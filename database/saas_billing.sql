create table if not exists public.voice_billing_purchases (
    transaction_id text primary key,
    user_id uuid not null references auth.users (id) on delete cascade,
    purchased_at timestamptz not null default now(),
    expires_at timestamptz not null,
    refunded_at timestamptz
);

create index if not exists voice_billing_purchases_user_expiry_idx
    on public.voice_billing_purchases (user_id, expires_at desc)
    where refunded_at is null;

create table if not exists public.voice_billing_events (
    event_id text primary key,
    event_type text not null,
    received_at timestamptz not null default now()
);

create table if not exists public.voice_billing_adjustments (
    transaction_id text primary key,
    refunded_at timestamptz not null
);

create table if not exists public.voice_stt_usage (
    request_id uuid primary key,
    user_id uuid not null references auth.users (id) on delete cascade,
    duration_seconds numeric(12, 3) not null,
    status text not null check (status in ('reserved', 'completed')),
    created_at timestamptz not null default now()
);

create index if not exists voice_stt_usage_user_created_idx
    on public.voice_stt_usage (user_id, created_at desc);

alter table public.voice_billing_purchases enable row level security;
alter table public.voice_billing_events enable row level security;
alter table public.voice_billing_adjustments enable row level security;
alter table public.voice_stt_usage enable row level security;

create or replace function public.apply_paddle_billing_event(
    p_event_id text,
    p_event_type text,
    p_payload jsonb,
    p_expected_price_id text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    event_data jsonb := coalesce(p_payload->'data', '{}'::jsonb);
    account_id uuid;
    target_transaction_id text;
    occurred_at timestamptz := coalesce((p_payload->>'occurred_at')::timestamptz, now());
    inserted_rows integer;
begin
    if p_event_id is null or p_event_id = '' then
        raise exception 'Missing Paddle event id';
    end if;

    insert into public.voice_billing_events (event_id, event_type)
    values (p_event_id, coalesce(p_event_type, ''))
    on conflict do nothing;
    get diagnostics inserted_rows = row_count;

    if inserted_rows = 0 then
        return jsonb_build_object('duplicate', true);
    end if;

    if p_event_type = 'transaction.completed' then
        target_transaction_id := event_data->>'id';

        if event_data->>'status' is distinct from 'completed'
            or target_transaction_id is null
            or not exists (
                select 1
                from jsonb_array_elements(coalesce(event_data->'items', '[]'::jsonb)) as item
                where coalesce(item->>'price_id', item->'price'->>'id') = p_expected_price_id
                  and coalesce(item->'price'->'billing_cycle', 'null'::jsonb) = 'null'::jsonb
                  and item->'price'->'unit_price'->>'amount' = '4990'
                  and item->'price'->'unit_price'->>'currency_code' = 'USD'
            )
        then
            return jsonb_build_object('ignored', true);
        end if;

        begin
            account_id := (event_data->'custom_data'->>'supabase_user_id')::uuid;
        exception when invalid_text_representation then
            return jsonb_build_object('ignored', true);
        end;

        if account_id is null then
            return jsonb_build_object('ignored', true);
        end if;

        insert into public.voice_billing_purchases
            (transaction_id, user_id, purchased_at, expires_at, refunded_at)
        values (
            target_transaction_id,
            account_id,
            occurred_at,
            greatest(
                occurred_at,
                coalesce((
                    select max(purchase.expires_at)
                    from public.voice_billing_purchases as purchase
                    where purchase.user_id = account_id
                      and purchase.refunded_at is null
                ), occurred_at)
            ) + interval '365 days',
            (
                select adjustment.refunded_at
                from public.voice_billing_adjustments as adjustment
                where adjustment.transaction_id = target_transaction_id
            )
        )
        on conflict (transaction_id) do nothing;

        return jsonb_build_object('credited', true);
    end if;

    if p_event_type in ('adjustment.created', 'adjustment.updated')
        and event_data->>'status' in ('approved', 'completed')
    then
        target_transaction_id := event_data->>'transaction_id';
        if target_transaction_id is not null then
            insert into public.voice_billing_adjustments (transaction_id, refunded_at)
            values (target_transaction_id, occurred_at)
            on conflict (transaction_id) do update
            set refunded_at = least(
                public.voice_billing_adjustments.refunded_at,
                excluded.refunded_at
            );
            update public.voice_billing_purchases
            set refunded_at = coalesce(refunded_at, occurred_at)
            where voice_billing_purchases.transaction_id = target_transaction_id;
            return jsonb_build_object('refunded', found);
        end if;
    end if;

    return jsonb_build_object('ignored', true);
end;
$$;

create or replace function public.get_voice_billing_status(
    p_user_id uuid,
    p_monthly_minutes numeric,
    p_window_days integer
)
returns jsonb
language sql
security definer
set search_path = ''
as $$
    with entitlement as (
        select max(expires_at) as expires_at
        from public.voice_billing_purchases
        where user_id = p_user_id
          and refunded_at is null
          and expires_at > now()
    ),
    usage as (
        select coalesce(sum(duration_seconds), 0) / 60.0 as used_minutes
        from public.voice_stt_usage
        where user_id = p_user_id
          and (
              status = 'completed'
              or created_at >= now() - interval '24 hours'
          )
          and created_at >= now() - make_interval(days => p_window_days)
    )
    select jsonb_build_object(
        'active', entitlement.expires_at is not null,
        'expires_at', entitlement.expires_at,
        'used_minutes', round(usage.used_minutes, 2),
        'remaining_minutes', greatest(0, round(p_monthly_minutes - usage.used_minutes, 2)),
        'monthly_limit_minutes', p_monthly_minutes,
        'window_days', p_window_days
    )
    from entitlement cross join usage;
$$;

create or replace function public.reserve_voice_stt_minutes(
    p_user_id uuid,
    p_duration_seconds numeric,
    p_request_id uuid,
    p_monthly_minutes numeric,
    p_window_days integer,
    p_max_job_seconds integer
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    used_seconds numeric;
    current_expiry timestamptz;
begin
    if p_duration_seconds <= 0 or p_duration_seconds > p_max_job_seconds then
        return jsonb_build_object('reserved', false, 'reason', 'duration_limit');
    end if;

    perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

    select max(expires_at)
    into current_expiry
    from public.voice_billing_purchases
    where user_id = p_user_id
      and refunded_at is null
      and expires_at > now();

    if current_expiry is null then
        return jsonb_build_object('reserved', false, 'reason', 'plan_required');
    end if;

    select coalesce(sum(duration_seconds), 0)
    into used_seconds
    from public.voice_stt_usage
    where user_id = p_user_id
      and (
          status = 'completed'
          or created_at >= now() - interval '24 hours'
      )
      and created_at >= now() - make_interval(days => p_window_days);

    if used_seconds + p_duration_seconds > p_monthly_minutes * 60 then
        return jsonb_build_object('reserved', false, 'reason', 'quota_exceeded');
    end if;

    insert into public.voice_stt_usage (request_id, user_id, duration_seconds, status)
    values (p_request_id, p_user_id, p_duration_seconds, 'reserved')
    on conflict (request_id) do nothing;

    if not found then
        return jsonb_build_object('reserved', false, 'reason', 'duplicate_request');
    end if;

    return jsonb_build_object('reserved', true, 'request_id', p_request_id);
end;
$$;

create or replace function public.finish_voice_stt_usage(
    p_request_id uuid,
    p_duration_seconds numeric,
    p_success boolean
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
begin
    if p_success then
        update public.voice_stt_usage
        set duration_seconds = greatest(0, p_duration_seconds),
            status = 'completed'
        where request_id = p_request_id
          and status = 'reserved';
        return found;
    end if;

    delete from public.voice_stt_usage
    where request_id = p_request_id
      and status = 'reserved';
    return found;
end;
$$;

revoke all on function public.apply_paddle_billing_event(text, text, jsonb, text) from public, anon, authenticated;
revoke all on function public.get_voice_billing_status(uuid, numeric, integer) from public, anon, authenticated;
revoke all on function public.reserve_voice_stt_minutes(uuid, numeric, uuid, numeric, integer, integer) from public, anon, authenticated;
revoke all on function public.finish_voice_stt_usage(uuid, numeric, boolean) from public, anon, authenticated;

grant execute on function public.apply_paddle_billing_event(text, text, jsonb, text) to service_role;
grant execute on function public.get_voice_billing_status(uuid, numeric, integer) to service_role;
grant execute on function public.reserve_voice_stt_minutes(uuid, numeric, uuid, numeric, integer, integer) to service_role;
grant execute on function public.finish_voice_stt_usage(uuid, numeric, boolean) to service_role;
