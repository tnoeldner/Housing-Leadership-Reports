# Future TODOs

- [ ] Add a unique index on saved_duty_analyses (week_ending_date, created_by, report_type) to support clean upserts.
- [ ] Simplify weekly duty summary saves to a single upsert once the unique index exists.
