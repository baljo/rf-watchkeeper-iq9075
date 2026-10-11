# Tower review configuration

Defaults are defined in `tower_review_policy.py`: detector reference 45.67438250526811, review floor 55, two adjacent 1-second windows with starts 0.5 seconds apart, audit 8%, stable salt `tower-grey-audit-v1:`. These are review settings, not model training settings. Do not alter the retained model threshold. No new private runtime configuration or migration is required; saved window evidence is evaluated read-only. Changing the salt changes audit membership and must be recorded. See [policy](../../docs/tower-anomaly.md).
