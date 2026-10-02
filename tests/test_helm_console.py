"""Tests for the helm console widgets: segmented gauges and keycap hints."""

from types import SimpleNamespace

from data.colors import CONSOLE_DIM, CONSOLE_FRAME, CONSOLE_LABEL, HP_GREEN, HP_RED, HP_YELLOW, KEYCAP_KEY, KEYCAP_LABEL
from ui.helm_console import Gauge, KeyHint, gauge_spans, keycap_spans, print_spans, ratio_color, spans_width

_COLOR = (1, 2, 3)


def _text(spans):
    return "".join(text for text, _ in spans)


class TestRatioColor:
    def test_green_above_half(self):
        assert ratio_color(0.75) == HP_GREEN

    def test_yellow_between_30_and_50_percent(self):
        assert ratio_color(0.4) == HP_YELLOW

    def test_red_below_30_percent(self):
        assert ratio_color(0.03) == HP_RED


def _cells(spans, color):
    """How many gauge cells are drawn in *color*."""
    return sum(text.count("■") for text, span_color in spans if span_color == color)


class TestGaugeSpans:
    def test_reads_label_cells_then_count(self):
        assert _text(gauge_spans(Gauge("FUEL", 8, 10, _COLOR))) == "FUEL ■■■■■■■■■■  8/10"

    def test_lit_cells_are_proportional_to_value(self):
        spans = gauge_spans(Gauge("FUEL", 8, 10, _COLOR))
        assert (_cells(spans, _COLOR), _cells(spans, CONSOLE_DIM)) == (8, 2)

    def test_full_gauge_has_no_unlit_cells(self):
        spans = gauge_spans(Gauge("HULL", 10, 10, _COLOR))
        assert (_cells(spans, _COLOR), _cells(spans, CONSOLE_DIM)) == (10, 0)
        assert _text(spans) == "HULL ■■■■■■■■■■ 10/10"

    def test_empty_gauge_has_no_lit_cells(self):
        spans = gauge_spans(Gauge("FUEL", 0, 10, _COLOR))
        assert (_cells(spans, _COLOR), _cells(spans, CONSOLE_DIM)) == (0, 10)
        assert all(text for text, _ in spans), "empty spans should be dropped"

    def test_zero_capacity_does_not_crash(self):
        assert _cells(gauge_spans(Gauge("FUEL", 0, 0, _COLOR)), _COLOR) == 0

    def test_any_remaining_value_lights_one_cell(self):
        assert _cells(gauge_spans(Gauge("FUEL", 6, 200, _COLOR)), _COLOR) == 1

    def test_all_cells_light_only_when_value_is_full(self):
        assert _cells(gauge_spans(Gauge("FUEL", 199, 200, _COLOR)), _COLOR) == 9

    def test_value_above_capacity_does_not_overflow(self):
        spans = gauge_spans(Gauge("FUEL", 15, 10, _COLOR))
        assert (_cells(spans, _COLOR), _cells(spans, CONSOLE_DIM)) == (10, 0)

    def test_width_sets_cell_count(self):
        spans = gauge_spans(Gauge("NAV", 3, 6, _COLOR, width=6))
        assert _text(spans) == "NAV ■■■■■■ 3/6"
        assert (_cells(spans, _COLOR), _cells(spans, CONSOLE_DIM)) == (3, 3)

    def test_readout_overrides_the_count(self):
        text = _text(gauge_spans(Gauge("NAV", 6, 6, _COLOR, readout="LOCKED", width=6)))
        assert text == "NAV ■■■■■■ LOCKED"

    def test_readout_carries_gauge_color(self):
        spans = gauge_spans(Gauge("FUEL", 8, 10, _COLOR))
        assert {text.strip(): color for text, color in spans}["8/10"] == _COLOR

    def test_label_stays_dim(self):
        spans = gauge_spans(Gauge("FUEL", 8, 10, _COLOR))
        assert {text.strip(): color for text, color in spans}["FUEL"] == CONSOLE_LABEL


class TestKeycapSpans:
    def test_hint_reads_key_then_label_without_brackets(self):
        text = _text(keycap_spans([[KeyHint("C", "Cargo")]]))
        assert text == "C Cargo"

    def test_key_is_brighter_than_label(self):
        spans = keycap_spans([[KeyHint("C", "Cargo")]])
        colors = {text.strip(): color for text, color in spans}
        assert colors["C"] == KEYCAP_KEY
        assert colors["Cargo"] == KEYCAP_LABEL

    def test_hints_in_a_group_are_spaced_apart(self):
        text = _text(keycap_spans([[KeyHint("C", "Cargo"), KeyHint("S", "Ship")]]))
        assert text == "C Cargo   S Ship"

    def test_groups_are_divided_by_a_rule(self):
        spans = keycap_spans([[KeyHint("C", "Cargo")], [KeyHint("Tab", "Locations")]])
        assert _text(spans) == "C Cargo   │   Tab Locations"
        assert (("│", CONSOLE_FRAME)) in [(text.strip(), color) for text, color in spans]

    def test_empty_groups_are_skipped(self):
        assert _text(keycap_spans([[], [KeyHint("C", "Cargo")]])) == "C Cargo"


class TestPrintSpans:
    def _console(self):
        printed = []
        console = SimpleNamespace()
        console.print = lambda *, x, y, string, fg=(255, 255, 255): printed.append((x, y, string, fg))
        return console, printed

    def test_spans_are_printed_end_to_end(self):
        console, printed = self._console()
        print_spans(console, 5, 7, [("ab", (1, 1, 1)), ("cde", (2, 2, 2))])
        assert printed == [(5, 7, "ab", (1, 1, 1)), (7, 7, "cde", (2, 2, 2))]

    def test_returns_x_after_last_span(self):
        console, _ = self._console()
        assert print_spans(console, 5, 7, [("ab", _COLOR), ("cde", _COLOR)]) == 10

    def test_spans_width_sums_text_lengths(self):
        assert spans_width([("ab", _COLOR), ("cde", _COLOR)]) == 5
