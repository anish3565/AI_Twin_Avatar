create or replace view api_usage_daily
with (security_invoker = true) as
select
    date_trunc('day', created_at)::date                    as day,
    coalesce(provider, 'unknown')                          as provider,
    count(*)                                               as requests,
    coalesce(sum(prompt_tokens), 0)
        + coalesce(sum(completion_tokens), 0)              as tokens,
    count(*) filter (where outcome = 'error')              as errors,
    count(*) filter (where fallback_used)                  as fallbacks
from messages
group by 1, 2;
