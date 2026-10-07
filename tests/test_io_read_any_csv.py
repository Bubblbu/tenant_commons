"""read_any_csv() feeds every raw_* ingest: it must pick the right delimiter
and keep values as the raw tables have always stored them."""

from tc_core.io import normalize_cols, read_any_csv


def _write(tmp_path, text, name="source.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _rows(df):
    return list(df.iter_rows())


def test_semicolon_files_keep_commas_inside_values(tmp_path):
    # City of Vancouver Open Data exports: ";"-delimited, "lat, lon" points.
    path = _write(tmp_path, "civic_number;geo_point_2d\n100;49.28, -123.13\n")
    df = read_any_csv(path)
    assert list(df.columns) == ["civic_number", "geo_point_2d"]
    assert _rows(df) == [(100, "49.28, -123.13")]


def test_comma_files_respect_quoted_commas(tmp_path):
    path = _write(tmp_path, 'id,address,rooms\n1,"210 Abbott St., Vancouver",63\n')
    assert _rows(read_any_csv(path)) == [(1, "210 Abbott St., Vancouver", 63)]


def test_empty_cells_are_missing_whether_quoted_or_not(tmp_path):
    # tc_core's own CSVs (e.g. derived/buildings.csv) write empty text as "".
    path = _write(tmp_path, 'a,b,c\nx,,""\n')
    assert _rows(read_any_csv(path)) == [("x", None, None)]


def test_types_are_inferred_from_the_whole_file(tmp_path):
    rows = "".join(f"{i}\n" for i in range(150)) + "BCS1010\n"
    path = _write(tmp_path, "site_id\n" + rows)
    assert read_any_csv(path)["site_id"][-1] == "BCS1010"


def test_a_single_column_file_reads(tmp_path):
    assert _rows(read_any_csv(_write(tmp_path, "geom\nPOINT (1 2)\n"))) == [("POINT (1 2)",)]


def test_normalize_cols_strips_bom_and_snake_cases(tmp_path):
    path = _write(tmp_path, "﻿Site ID,# Registered Rooms\n1,2\n")
    assert list(normalize_cols(read_any_csv(path)).columns) == ["site_id", "#_registered_rooms"]
