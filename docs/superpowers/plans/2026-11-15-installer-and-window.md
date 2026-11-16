# Plan: installer, one folder, calmer window

Spec: `docs/superpowers/specs/2026-11-15-installer-and-window-design.md`. Branch `feat/installer`.

1. **`version.py`, folders, migration.** `VERSION`; `paths.DATA_DIR/CACHE_DIR/LOGS_DIR/DEBUG_DIR/REPORTS_DIR`;
   `paths.migrate(app_dir)` moves loose data files into `data\`. Tests: moves, keeps an existing
   `data\` file, no-op when nothing is loose. Point `companion.PROFILE`, `sniper.CONFIG/DB`, the grind
   db, `discord_link.OUTBOX`, `tools/grab_samples.py` at `DATA_DIR`. `.gitignore`: `data/ logs/ reports/`.
2. **`applog.py`.** `setup(dir, sink)`, `say`, `log`, `problem(kind, text, exc)`, daily file name,
   7-day cleanup, `stdout/stderr` to the file, `threading.excepthook`. Tests with a fake clock and
   sink: say reaches both, log only the file, a problem kind shows once per 10 min but is always
   logged, old files deleted, printed text lands in the file only.
3. **Calls.** Each `print` becomes `say`, `log` or `problem` as the spec lists; tracebacks go through
   `problem(..., exc=e)` or `log`. `--report` (CLI) keeps printing.
4. **Window.** Lines with time, problems in amber, a footer with Report a problem; it reads from the
   applog sink instead of replacing `stdout`.
5. **`report.py`.** `make(app_dir, cfg)` writes the zip (3 days of logs, `info.txt`, settings without
   Discord fields). Tests: contents, no `profile.json`, no pictures, Discord fields gone. The button
   then selects it in Explorer and opens the issue form.
6. **Single instance.** A named mutex `Tura2.Companion` the installer can wait on (`AppMutex`).
7. **Build.** `build.bat`: PyInstaller one-folder, then ISCC with the version →
   `dist\CompanionSetup.exe`. `installer/companion.iss`: per user, English + Hebrew, shortcuts,
   launch at the end, `AppMutex`, uninstall asks about `data\`.
8. **Links and docs.** Site (EN and HE) and README Download → `CompanionSetup.exe`; install steps
   say "run the setup"; README "Your data" and release steps updated.
9. **Check.** `pytest`; build; silent install into a scratch folder, run, see the folders, uninstall
   both ways (keep data / delete data); smoke-run from source.
