# Duplicate users

## What we found

`Exercise_users.csv` has 806 rows and 800 distinct `user_id` values. Six ids appear twice:

- USR_00064
- USR_00067
- USR_00534
- USR_00622
- USR_00668
- USR_00697

Each pair matches on every column, including email.

## Treatment

Keep the first row for each `user_id` and drop the copy. `dim_user` has 800 rows.

## Check to enforce

Fail the build if `dim_user` contains a repeated `user_id`. If a new raw pair is identical, drop it the same way. If a new raw pair disagrees on any column, stop the build and decide which row wins before the model is published.
