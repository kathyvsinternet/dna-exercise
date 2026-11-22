-- intermediate model for the calendar date spine

SELECT CAST(date AS DATE) AS date
FROM generate_series(DATE '2021-01-01', DATE '2026-10-12', INTERVAL 1 DAY) AS spine(date)
