import unittest

from ashare_v3.market.hint_1m_projection_proof import (
    build_index_board_1m_hint_projection_proof,
    index_board_hint_30m_window_for_minute,
)


class N3HintIndexBoard1mProjectionProofTest(unittest.TestCase):
    def test_window_mapping_uses_canonical_sessions(self) -> None:
        window = index_board_hint_30m_window_for_minute("2026-06-29T10:12:00+08:00")

        self.assertEqual(window["current_window_start"], "10:01")
        self.assertEqual(window["current_window_end"], "10:30")
        self.assertEqual(window["previous_completed_window_start"], "09:31")
        self.assertEqual(window["previous_completed_window_end"], "10:00")
        self.assertEqual(window["elapsed_labels"], [f"10:{minute:02d}" for minute in range(1, 13)])
        self.assertNotIn("11:30", window["full_window_labels"])

    def test_1300_maps_after_lunch_without_1130_fake_bar(self) -> None:
        window = index_board_hint_30m_window_for_minute("13:00")

        self.assertEqual(window["current_window_start"], "11:01")
        self.assertEqual(window["current_window_end"], "11:30")
        self.assertEqual(window["previous_completed_window_start"], "10:31")
        self.assertEqual(window["previous_completed_window_end"], "11:00")
        self.assertEqual(window["closed_status"], "closed")
        self.assertEqual(window["elapsed_labels"], labels_between("11:01", "11:30"))
        self.assertEqual(window["current_window_raw_elapsed_labels"][-1], "13:00")
        self.assertEqual(window["current_window_logical_elapsed_labels"][-1], "11:30")
        self.assertEqual(window["midday_bridge_policy"], "hint_1300_as_1130_close_v1")

    def test_1300_bridge_uses_raw_1300_for_logical_1130_full_window(self) -> None:
        proof = build_index_board_1m_hint_projection_proof(
            asset_kind="board",
            identity_key="board:TDX:881442",
            for_trade_date="20260629",
            previous_trade_date="20260626",
            proof_input_time="2026-06-29T13:00:00+08:00",
            current_day_1m_rows=current_rows_for_1300_bridge(
                asset_kind="board",
                identity_key="board:TDX:881442",
                previous_completed_close=100,
                latest_close=90,
                current_amount=5,
            ),
            previous_day_1m_rows=previous_rows_for_1101_window(
                asset_kind="board",
                identity_key="board:TDX:881442",
                amount=10,
            ),
        )

        self.assertTrue(proof["valid"], proof["blocked_reasons"])
        self.assertEqual(proof["current_window_start"], "11:01")
        self.assertEqual(proof["current_window_end"], "11:30")
        self.assertEqual(proof["closed_status"], "closed")
        self.assertEqual(proof["current_window_elapsed_count"], 30)
        self.assertEqual(proof["current_window_raw_elapsed_labels"][-1], "13:00")
        self.assertEqual(proof["current_window_logical_elapsed_labels"][-1], "11:30")
        self.assertEqual(proof["current_30m_elapsed_amount"], 150.0)
        self.assertEqual(proof["previous_day_same_elapsed_30m_amount"], 300.0)
        self.assertEqual(proof["previous_day_full_30m_amount"], 300.0)
        self.assertEqual(proof["current_30m_virtual_amount"], 150.0)
        self.assertEqual(proof["projection_30m_type"], "shrink_down")

    def test_1301_starts_afternoon_window_without_1300_bridge_row(self) -> None:
        proof = build_index_board_1m_hint_projection_proof(
            asset_kind="board",
            identity_key="board:TDX:881442",
            for_trade_date="20260629",
            previous_trade_date="20260626",
            proof_input_time="2026-06-29T13:01:00+08:00",
            current_day_1m_rows=current_rows_for_1301(
                asset_kind="board",
                identity_key="board:TDX:881442",
                latest_close=110,
                current_amount=20,
            ),
            previous_day_1m_rows=rows_for_labels(
                "board",
                "board:TDX:881442",
                "20260626",
                labels_between("13:01", "13:30"),
                amount=10,
            ),
        )

        self.assertTrue(proof["valid"], proof["blocked_reasons"])
        self.assertEqual(proof["current_window_start"], "13:01")
        self.assertEqual(proof["current_window_end"], "13:30")
        self.assertEqual(proof["previous_completed_window_start"], "11:01")
        self.assertEqual(proof["previous_completed_window_end"], "11:30")
        self.assertEqual(proof["current_window_elapsed_labels"], ["13:01"])
        self.assertNotIn("13:00", proof["current_window_elapsed_labels"])

    def test_current_day_raw_1130_and_duplicate_bridge_fail_closed(self) -> None:
        real_1130 = rows_for_labels("board", "board:TDX:881442", "20260629", ["11:30"])
        duplicate_bridge = current_rows_for_1300_bridge(asset_kind="board", identity_key="board:TDX:881442") + real_1130
        cases = [
            (real_1130, "canonical_1130_forbidden"),
            (duplicate_bridge, "duplicate_canonical_label"),
        ]
        for current_rows, reason in cases:
            with self.subTest(reason=reason):
                proof = build_index_board_1m_hint_projection_proof(
                    asset_kind="board",
                    identity_key="board:TDX:881442",
                    for_trade_date="20260629",
                    previous_trade_date="20260626",
                    proof_input_time="2026-06-29T13:00:00+08:00",
                    current_day_1m_rows=current_rows,
                    previous_day_1m_rows=previous_rows_for_1101_window(
                        asset_kind="board",
                        identity_key="board:TDX:881442",
                    ),
                )

                self.assertFalse(proof["valid"])
                self.assertIn(reason, proof["blocked_reasons"])

    def test_first_window_uses_previous_trade_date_last_30m_entity_reference(self) -> None:
        proof = build_index_board_1m_hint_projection_proof(
            asset_kind="index",
            identity_key="index:SH:000016",
            for_trade_date="20260629",
            previous_trade_date="20260626",
            proof_input_time="2026-06-29T09:45:00+08:00",
            current_day_1m_rows=rows_for_labels("index", "index:SH:000016", "20260629", labels_between("09:31", "09:45")),
            previous_day_1m_rows=previous_rows_for_first_window(
                open_value=98,
                close_value=102,
                same_window_amount=10,
            ),
        )

        self.assertTrue(proof["valid"], proof["blocked_reasons"])
        self.assertEqual(proof["previous_completed_window_start"], "14:31")
        self.assertEqual(proof["previous_completed_window_end"], "15:00")
        self.assertEqual(proof["previous_completed_window_source"], "previous_trade_date_last_30m")
        self.assertEqual(proof["previous_day_same_elapsed_30m_amount"], 150.0)
        self.assertEqual(proof["previous_day_full_30m_amount"], 300.0)
        self.assertEqual(proof["reference_30m_entity_high"], 102.0)
        self.assertEqual(proof["reference_30m_entity_low"], 98.0)
        self.assertNotIn("first_30m_window_no_previous_completed_window", proof["blocked_reasons"])

    def test_first_window_fails_closed_when_previous_trade_date_last_30m_reference_missing(self) -> None:
        proof = build_index_board_1m_hint_projection_proof(
            asset_kind="index",
            identity_key="index:SH:000016",
            for_trade_date="20260629",
            previous_trade_date="20260626",
            proof_input_time="2026-06-29T09:45:00+08:00",
            current_day_1m_rows=rows_for_labels("index", "index:SH:000016", "20260629", labels_between("09:31", "09:45")),
            previous_day_1m_rows=rows_for_labels("index", "index:SH:000016", "20260626", labels_between("09:31", "10:00")),
        )

        self.assertFalse(proof["valid"])
        self.assertEqual(proof["projection_30m_type"], "unknown")
        self.assertIn("missing_previous_trade_date_last_30m_open_close", proof["blocked_reasons"])

    def test_buy_hint_volume_up_proof(self) -> None:
        proof = build_index_board_1m_hint_projection_proof(
            asset_kind="index",
            identity_key="index:SH:000016",
            for_trade_date="20260629",
            previous_trade_date="20260626",
            proof_input_time="2026-06-29T10:12:00+08:00",
            current_day_1m_rows=current_rows_for_1012(previous_completed_close=105, latest_close=110, current_amount=20),
            previous_day_1m_rows=previous_rows_for_1001_window(amount=10),
            projection_run_id="n3_hint_projection_20260629_until_1012",
            projection_id=1012,
        )

        self.assertTrue(proof["valid"])
        self.assertEqual(proof["proof_kind"], "index_board_1m_hint_projection_v1")
        self.assertEqual(proof["source_mode"], "index_board_frequency8_1m")
        self.assertEqual(proof["metric_role"], "hint_trigger_proof")
        self.assertEqual(proof["proof_owner"], "N3")
        self.assertEqual(proof["proof_consumer"], "N4")
        self.assertTrue(proof["not_n5_final_proof"])
        self.assertEqual(proof["current_window_start"], "10:01")
        self.assertEqual(proof["current_window_end"], "10:30")
        self.assertEqual(proof["previous_completed_window_start"], "09:31")
        self.assertEqual(proof["previous_completed_window_end"], "10:00")
        self.assertEqual(proof["current_30m_price"], 110.0)
        self.assertEqual(proof["current_30m_elapsed_amount"], 240.0)
        self.assertEqual(proof["previous_day_same_elapsed_30m_amount"], 120.0)
        self.assertEqual(proof["previous_day_full_30m_amount"], 300.0)
        self.assertEqual(proof["current_30m_virtual_amount"], 600.0)
        self.assertEqual(proof["reference_30m_amount"], 300.0)
        self.assertEqual(proof["reference_30m_entity_high"], 105.0)
        self.assertEqual(proof["reference_30m_entity_low"], 100.0)
        self.assertEqual(proof["projection_30m_type"], "volume_up")
        self.assertTrue(proof["projection_30m_flag"])

    def test_sell_hint_shrink_down_proof(self) -> None:
        proof = build_index_board_1m_hint_projection_proof(
            asset_kind="board",
            identity_key="board:TDX:881001",
            for_trade_date="20260629",
            previous_trade_date="20260626",
            proof_input_time="2026-06-29T10:12:00+08:00",
            current_day_1m_rows=current_rows_for_1012(
                asset_kind="board",
                identity_key="board:TDX:881001",
                previous_completed_close=95,
                latest_close=90,
                current_amount=5,
            ),
            previous_day_1m_rows=previous_rows_for_1001_window(
                asset_kind="board",
                identity_key="board:TDX:881001",
                amount=10,
            ),
        )

        self.assertTrue(proof["valid"])
        self.assertEqual(proof["projection_30m_type"], "shrink_down")
        self.assertTrue(proof["projection_30m_flag"])
        self.assertEqual(proof["reference_30m_entity_high"], 100.0)
        self.assertEqual(proof["reference_30m_entity_low"], 95.0)

    def test_none_when_required_fields_exist_but_conditions_do_not_match(self) -> None:
        proof = build_index_board_1m_hint_projection_proof(
            asset_kind="index",
            identity_key="index:SH:000016",
            for_trade_date="20260629",
            previous_trade_date="20260626",
            proof_input_time="2026-06-29T10:12:00+08:00",
            current_day_1m_rows=current_rows_for_1012(previous_completed_close=105, latest_close=103, current_amount=10),
            previous_day_1m_rows=previous_rows_for_1001_window(amount=10),
        )

        self.assertTrue(proof["valid"])
        self.assertEqual(proof["projection_30m_type"], "none")
        self.assertFalse(proof["projection_30m_flag"])

    def test_stock_is_not_applicable(self) -> None:
        proof = build_index_board_1m_hint_projection_proof(
            asset_kind="stock",
            identity_key="stock:SH:600000",
            for_trade_date="20260629",
            previous_trade_date="20260626",
            proof_input_time="2026-06-29T10:12:00+08:00",
            current_day_1m_rows=[],
            previous_day_1m_rows=[],
        )

        self.assertFalse(proof["valid"])
        self.assertIn("asset_kind_not_applicable", proof["blocked_reasons"])
        self.assertEqual(proof["not_ready_classification"], "not_applicable")

    def test_fail_closed_for_duplicate_label_1130_source_mismatch_and_fake_marker(self) -> None:
        cases = [
            (
                current_rows_for_1012() + [current_rows_for_1012()[0]],
                previous_rows_for_1001_window(),
                "duplicate_canonical_label",
            ),
            (
                rows_for_labels("index", "index:SH:000016", "20260629", ["09:31", "11:30"]),
                previous_rows_for_1001_window(),
                "canonical_1130_forbidden",
            ),
            (
                current_rows_for_1012(source_trade_date="20260628"),
                previous_rows_for_1001_window(),
                "source_trade_date_mismatch",
            ),
            (
                current_rows_for_1012(source_marker="fake"),
                previous_rows_for_1001_window(),
                "fake_source_marker",
            ),
        ]
        for current_rows, previous_rows, reason in cases:
            with self.subTest(reason=reason):
                proof = build_index_board_1m_hint_projection_proof(
                    asset_kind="index",
                    identity_key="index:SH:000016",
                    for_trade_date="20260629",
                    previous_trade_date="20260626",
                    proof_input_time="2026-06-29T10:12:00+08:00",
                    current_day_1m_rows=current_rows,
                    previous_day_1m_rows=previous_rows,
                )

                self.assertFalse(proof["valid"])
                self.assertEqual(proof["projection_30m_type"], "unknown")
                self.assertIn(reason, proof["blocked_reasons"])

    def test_fail_closed_for_missing_previous_rows_and_non_positive_previous_elapsed(self) -> None:
        missing_previous = build_index_board_1m_hint_projection_proof(
            asset_kind="index",
            identity_key="index:SH:000016",
            for_trade_date="20260629",
            previous_trade_date="20260626",
            proof_input_time="2026-06-29T10:12:00+08:00",
            current_day_1m_rows=current_rows_for_1012(),
            previous_day_1m_rows=previous_rows_for_1001_window(amount=10)[:-1],
        )
        non_positive = build_index_board_1m_hint_projection_proof(
            asset_kind="index",
            identity_key="index:SH:000016",
            for_trade_date="20260629",
            previous_trade_date="20260626",
            proof_input_time="2026-06-29T10:12:00+08:00",
            current_day_1m_rows=current_rows_for_1012(),
            previous_day_1m_rows=previous_rows_for_1001_window(amount=0),
        )

        self.assertIn("missing_previous_day_full_30m_rows", missing_previous["blocked_reasons"])
        self.assertIn("previous_day_same_elapsed_30m_amount_non_positive", non_positive["blocked_reasons"])


def current_rows_for_1012(
    *,
    asset_kind: str = "index",
    identity_key: str = "index:SH:000016",
    previous_completed_close: float = 105.0,
    latest_close: float = 110.0,
    current_amount: float = 20.0,
    source_trade_date: str = "20260629",
    source_marker: str = "mootdx_index_frequency_8",
) -> list[dict[str, object]]:
    rows = rows_for_labels(
        asset_kind,
        identity_key,
        source_trade_date,
        labels_between("09:31", "10:00"),
        open_value=100,
        close_value=previous_completed_close,
        amount=1,
        source_marker=source_marker,
    )
    rows.extend(
        rows_for_labels(
            asset_kind,
            identity_key,
            source_trade_date,
            labels_between("10:01", "10:12"),
            open_value=latest_close,
            close_value=latest_close,
            amount=current_amount,
            source_marker=source_marker,
        )
    )
    return rows


def previous_rows_for_1001_window(
    *,
    asset_kind: str = "index",
    identity_key: str = "index:SH:000016",
    amount: float = 10.0,
) -> list[dict[str, object]]:
    return rows_for_labels(
        asset_kind,
        identity_key,
        "20260626",
        labels_between("10:01", "10:30"),
        amount=amount,
    )


def previous_rows_for_first_window(
    *,
    asset_kind: str = "index",
    identity_key: str = "index:SH:000016",
    same_window_amount: float = 10.0,
    open_value: float = 100.0,
    close_value: float = 100.0,
) -> list[dict[str, object]]:
    rows = rows_for_labels(
        asset_kind,
        identity_key,
        "20260626",
        labels_between("09:31", "10:00"),
        amount=same_window_amount,
    )
    rows.extend(
        rows_for_labels(
            asset_kind,
            identity_key,
            "20260626",
            labels_between("14:31", "15:00"),
            open_value=open_value,
            close_value=close_value,
            amount=1,
        )
    )
    return rows


def current_rows_for_1300_bridge(
    *,
    asset_kind: str = "index",
    identity_key: str = "index:SH:000016",
    previous_completed_close: float = 100.0,
    latest_close: float = 90.0,
    current_amount: float = 5.0,
    source_trade_date: str = "20260629",
    source_marker: str = "mootdx_index_frequency_8",
) -> list[dict[str, object]]:
    rows = rows_for_labels(
        asset_kind,
        identity_key,
        source_trade_date,
        labels_between("10:31", "11:00"),
        open_value=100,
        close_value=previous_completed_close,
        amount=1,
        source_marker=source_marker,
    )
    rows.extend(
        rows_for_labels(
            asset_kind,
            identity_key,
            source_trade_date,
            labels_between("11:01", "11:29"),
            open_value=latest_close,
            close_value=latest_close,
            amount=current_amount,
            source_marker=source_marker,
        )
    )
    rows.extend(
        rows_for_labels(
            asset_kind,
            identity_key,
            source_trade_date,
            ["13:00"],
            open_value=latest_close,
            close_value=latest_close,
            amount=current_amount,
            source_marker=source_marker,
        )
    )
    return rows


def current_rows_for_1301(
    *,
    asset_kind: str = "index",
    identity_key: str = "index:SH:000016",
    previous_completed_close: float = 100.0,
    latest_close: float = 110.0,
    current_amount: float = 20.0,
    source_trade_date: str = "20260629",
    source_marker: str = "mootdx_index_frequency_8",
) -> list[dict[str, object]]:
    rows = rows_for_labels(
        asset_kind,
        identity_key,
        source_trade_date,
        labels_between("11:01", "11:29"),
        open_value=100,
        close_value=previous_completed_close,
        amount=1,
        source_marker=source_marker,
    )
    rows.extend(
        rows_for_labels(
            asset_kind,
            identity_key,
            source_trade_date,
            ["13:00"],
            open_value=previous_completed_close,
            close_value=previous_completed_close,
            amount=1,
            source_marker=source_marker,
        )
    )
    rows.extend(
        rows_for_labels(
            asset_kind,
            identity_key,
            source_trade_date,
            ["13:01"],
            open_value=latest_close,
            close_value=latest_close,
            amount=current_amount,
            source_marker=source_marker,
        )
    )
    return rows


def previous_rows_for_1101_window(
    *,
    asset_kind: str = "index",
    identity_key: str = "index:SH:000016",
    amount: float = 10.0,
) -> list[dict[str, object]]:
    return rows_for_labels(
        asset_kind,
        identity_key,
        "20260626",
        labels_between("11:01", "11:30"),
        amount=amount,
    )


def rows_for_labels(
    asset_kind: str,
    identity_key: str,
    trade_date: str,
    labels: list[str],
    *,
    open_value: float = 100.0,
    close_value: float = 100.0,
    amount: float = 10.0,
    source_marker: str = "mootdx_index_frequency_8",
) -> list[dict[str, object]]:
    iso_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
    rows: list[dict[str, object]] = []
    for label in labels:
        rows.append(
            {
                "asset_kind": asset_kind,
                "identity_key": identity_key,
                "trade_date": trade_date,
                "bar_time": f"{iso_date}T{label}:00+08:00",
                "open": open_value,
                "close": close_value,
                "amount": amount,
                "source_marker": source_marker,
            }
        )
    return rows


def labels_between(start: str, end: str) -> list[str]:
    labels = []
    hour, minute = [int(part) for part in start.split(":")]
    end_hour, end_minute = [int(part) for part in end.split(":")]
    while (hour, minute) <= (end_hour, end_minute):
        labels.append(f"{hour:02d}:{minute:02d}")
        minute += 1
        if minute == 60:
            hour += 1
            minute = 0
    return labels


if __name__ == "__main__":
    unittest.main()
