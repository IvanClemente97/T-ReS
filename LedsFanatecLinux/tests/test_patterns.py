import unittest

from leds_fanatec_linux.models import LedProfile, default_profile
from leds_fanatec_linux.patterns import FLAG_ZONES, RPM_ZONES, FlagPattern, RpmPattern
from leds_fanatec_linux.telemetry import parse_rivals_snapshot


def telemetry(**kwargs):
    values = {
        "rpm": 2000,
        "max_rpm": 10000,
        "speed_kmh": 0,
        "gear": 1,
        "throttle": 0,
        "brake": 0,
        "is_in_pit_lane": False,
        "pit_limiter_on": False,
        "flags": 0,
    }
    values.update(kwargs)
    return parse_rivals_snapshot(
        {"version": 4, "player_telemetry": values},
        "Fanatec Rivals bridge",
        1.0,
    )


class PatternTests(unittest.TestCase):
    def test_rpm_sequence_can_move_from_left_to_right_or_outer_to_center(self):
        profile = default_profile()
        pattern = RpmPattern().calculate(2000, 10000, profile, blink_on=True)
        self.assertNotEqual(pattern["RPM1"], (0, 0, 0))
        self.assertEqual(pattern["RPM2"], (0, 0, 0))
        self.assertEqual(pattern["RPM3"], (0, 0, 0))
        pattern = RpmPattern().calculate(2500, 10000, profile, blink_on=True)
        self.assertNotEqual(pattern["RPM2"], (0, 0, 0))

        outer_profile = LedProfile(
            profile_id=profile.profile_id,
            name=profile.name,
            rpm_colors=profile.rpm_colors,
            max_rpm_colors=profile.max_rpm_colors,
            sequence="outer_to_center",
        )
        outer = RpmPattern().calculate(2000, 10000, outer_profile, blink_on=True)
        self.assertNotEqual(outer["RPM1"], (0, 0, 0))
        self.assertEqual(outer["RPM9"], (0, 0, 0))
        self.assertEqual(outer["RPM2"], (0, 0, 0))
        outer = RpmPattern().calculate(2500, 10000, outer_profile, blink_on=True)
        self.assertNotEqual(outer["RPM9"], (0, 0, 0))

    def test_each_rpm_led_uses_an_individual_fraction_of_telemetry_max(self):
        profile = default_profile()
        calculator = RpmPattern()
        below_threshold = calculator.calculate(1099, 9900, profile, blink_on=True)
        self.assertEqual(set(below_threshold.values()), {(0, 0, 0)})
        at_threshold = calculator.calculate(1100, 9900, profile, blink_on=True)
        self.assertEqual(sum(color != (0, 0, 0) for color in at_threshold.values()), 1)

    def test_max_rpm_uses_nine_profile_colors_and_blinks_at_telemetry_limit(self):
        profile = default_profile()
        colors = tuple(f"#{index:02X}00FF" for index in range(1, 10))
        profile = LedProfile(
            profile_id=profile.profile_id,
            name=profile.name,
            rpm_colors=profile.rpm_colors,
            max_rpm_colors=colors,
            sequence=profile.sequence,
        )
        calculator = RpmPattern()
        below_limit = calculator.calculate(9999, 10000, profile, blink_on=True)
        self.assertEqual(below_limit["RPM9"], (0, 0, 0))
        self.assertEqual(
            sum(color != (0, 0, 0) for color in below_limit.values()), 8
        )
        at_limit = calculator.calculate(10000, 10000, profile, blink_on=True)
        self.assertEqual(
            tuple(at_limit[zone] for zone in RPM_ZONES),
            tuple((index, 0, 255) for index in range(1, 10)),
        )
        blink_off = calculator.calculate(10000, 10000, profile, blink_on=False)
        self.assertEqual(set(blink_off.values()), {(0, 0, 0)})

    def test_missing_telemetry_max_rpm_keeps_rpm_off(self):
        profile = default_profile()
        pattern = RpmPattern().calculate(8000, None, profile, blink_on=True)
        self.assertEqual(set(pattern.values()), {(0, 0, 0)})

    def test_max_rpm_blink_period_controls_the_test_pattern(self):
        profile = default_profile()
        profile = LedProfile(
            profile_id=profile.profile_id,
            name=profile.name,
            rpm_colors=profile.rpm_colors,
            max_rpm_colors=profile.max_rpm_colors,
            sequence=profile.sequence,
            max_rpm_blink_ms=1000,
        )
        calculator = RpmPattern()
        self.assertTrue(all(color != (0, 0, 0) for color in calculator.test_frame(profile, 0, max_rpm=True).values()))
        self.assertTrue(all(color != (0, 0, 0) for color in calculator.test_frame(profile, 0.49, max_rpm=True).values()))
        self.assertEqual(set(calculator.test_frame(profile, 0.5, max_rpm=True).values()), {(0, 0, 0)})

    def test_flag_leds_remain_off_when_flags_are_unavailable(self):
        sample = telemetry()
        pattern = FlagPattern().calculate(sample, now=2.0)
        self.assertEqual(set(pattern.values()), {(0, 0, 0)})
        unavailable = type(sample)(
            simulator=sample.simulator,
            source=sample.source,
            received_at=sample.received_at,
            flags_available=False,
        )
        pattern = FlagPattern().calculate(unavailable, now=2.0)
        self.assertEqual(set(pattern.values()), {(0, 0, 0)})

    def test_yellow_variants_have_fixed_distinct_patterns(self):
        calculator = FlagPattern()
        yellow = calculator.calculate_test("yellow", now=0.0)
        self.assertEqual(set(yellow.values()), {(255, 255, 0)})

        left = calculator.calculate_test("double_yellow", now=0.0)
        right = calculator.calculate_test("double_yellow", now=0.25)
        self.assertEqual(set(left.values()), {(255, 255, 0), (0, 0, 0)})
        self.assertTrue(all(left[zone] != right[zone] for zone in FLAG_ZONES))

        first = calculator.calculate_test("local_yellow", now=0.0)
        second = calculator.calculate_test("local_yellow", now=0.25)
        self.assertEqual(first["LFLAG1"], (255, 255, 0))
        self.assertEqual(second["LFLAG2"], (255, 255, 0))
        self.assertNotEqual(first, second)

    def test_black_flag_preserves_its_alternating_pattern(self):
        pattern = FlagPattern().calculate(telemetry(flags=3), now=0.0)
        expected = {(255, 255, 255), (0, 0, 0)}
        self.assertEqual(set(pattern.values()), expected)

    def test_pit_limiter_keeps_the_existing_left_right_amber_magenta_pattern(self):
        calculator = FlagPattern()
        left = calculator.calculate(
            telemetry(is_in_pit_lane=True, pit_limiter_on=True), now=0.0
        )
        right = calculator.calculate(
            telemetry(is_in_pit_lane=True, pit_limiter_on=True), now=0.25
        )
        self.assertEqual(set(left.values()), {(255, 140, 0), (0, 0, 0)})
        self.assertEqual(set(right.values()), {(255, 0, 255), (0, 0, 0)})

    def test_rpm_and_flag_zone_counts_match_hardware(self):
        self.assertEqual(len(RPM_ZONES), 9)
        self.assertEqual(len(FLAG_ZONES), 6)


if __name__ == "__main__":
    unittest.main()
