from modules import fluency_check as fc


def test_bullet_dimension_dedup_passes_when_headers_cover_distinct_dimensions():
    bullets = [
        'LONG BATTERY LIFE — Record up to 150 minutes on one charge.',
        '1080P VIDEO DETAIL — Capture crisp clips for daily vlogging.',
        'MAGNETIC CLIP WEAR — Snap onto a shirt or strap in seconds.',
        'KIT READY VALUE — Includes the accessories you need to start fast.',
        'BEST-USE GUIDANCE — Ideal for daily carry, not heavy vibration sports.',
    ]

    result = fc.check_bullet_dimension_dedup(bullets)

    assert result['pass'] is True
    assert result['affected_bullets'] == []


def test_bullet_dimension_dedup_fails_when_three_bullets_repeat_commute_dimension():
    bullets = [
        'COMMUTE READY POV — Clip on and capture every train ride hands-free.',
        'BIKE CLIP VIEW — Stay ready for cycling routes and quick street moments.',
        'DAILY RIDE RECORDING — Keep spontaneous commute footage easy to catch.',
        'KIT READY VALUE — Includes the accessories you need to start fast.',
        'LONG BATTERY LIFE — Record up to 150 minutes on one charge.',
    ]

    result = fc.check_bullet_dimension_dedup(bullets)

    assert result['pass'] is False
    assert result['issue'] == 'dimension_repeat'
    assert result['duplicated_dimension'] == 'mobility_commute'
    assert result['affected_bullets'] == [1, 2, 3]


def test_bullet_dimension_dedup_allows_two_repeats_without_triggering():
    bullets = [
        'COMMUTE READY POV — Clip on and capture every train ride hands-free.',
        'TRAVEL CLIP VIEW — Stay ready for daily rides and quick street moments.',
        'LONG BATTERY LIFE — Record up to 150 minutes on one charge.',
        'KIT READY VALUE — Includes the accessories you need to start fast.',
        'BEST-USE GUIDANCE — Ideal for daily carry, not heavy vibration sports.',
    ]

    result = fc.check_bullet_dimension_dedup(bullets)

    assert result['pass'] is True


def test_bullet_total_bytes_reports_soft_limit():
    bullets = ['A' * 210] * 5

    result = fc.check_bullet_total_bytes(bullets)

    assert result['pass'] is False
    assert result['severity'] == 'soft'
    assert result['limit'] == 1000
