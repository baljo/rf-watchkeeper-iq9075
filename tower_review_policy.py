"""Pure human queue selection; never changes model, capture or retention."""
import hashlib
import math

DETECTOR_THRESHOLD = 45.67438250526811
REVIEW_THRESHOLD = 55.0
AUDIT_PERCENT = 8
AUDIT_SALT = 'tower-grey-audit-v1:'


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def persistent(windows):
    """Two successive valid 1 s windows >=55 with starts exactly 0.5 s apart."""
    previous = None
    for window in windows if isinstance(windows, list) else []:
        if not isinstance(window, dict):
            previous = None
            continue
        start, end, score = (window.get(k) for k in ('start_seconds', 'end_seconds', 'anomaly_score'))
        valid = (all(finite(v) for v in (start, end, score)) and start >= 0 and
                 abs(end-start-1.0) <= 1e-6 and score >= REVIEW_THRESHOLD)
        if valid and previous is not None and abs(start-previous-0.5) <= 1e-6:
            return True
        previous = start if valid else None
    return False


def audit_selected(capture_id):
    if not isinstance(capture_id, str) or not capture_id:
        return False
    digest = hashlib.sha256((AUDIT_SALT+capture_id).encode('utf-8')).digest()
    return int.from_bytes(digest, 'big') % 100 < AUDIT_PERCENT


def metadata(evidence, capture_id):
    score = evidence['summary']['p100']
    persistence = persistent(evidence.get('windows'))
    audit = DETECTOR_THRESHOLD <= score < REVIEW_THRESHOLD and audit_selected(capture_id)
    return dict(review_threshold=REVIEW_THRESHOLD, review_persistent=persistence,
                grey_zone_audit=audit, review_policy='tower-review-v1',
                review_selection_reason=('persistent_ad' if score >= REVIEW_THRESHOLD and persistence
                                         else 'grey_zone_audit' if audit else 'hidden'))


def selection_reason(row):
    review = row.get('anomaly_review') or {}
    label = (row.get('human_review') or {}).get('human_review_label') or review.get('review_state')
    if label and label != 'unreviewed':
        return None
    if (review.get('scoring_status') != 'scored' or not finite(review.get('score')) or
            not finite(review.get('threshold')) or row.get('audio_available') is False):
        return None
    if row.get('explicit_review_override') is True:
        return 'explicit_override'
    score = review['score']
    if score < DETECTOR_THRESHOLD:
        return None
    if score < REVIEW_THRESHOLD:
        return 'grey_zone_audit' if audit_selected(row.get('recording')) else None
    return 'persistent_ad' if review.get('review_persistent') is True else None
