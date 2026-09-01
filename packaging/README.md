# Building the Lapus desktop app

Produces a folder a non-technical user can double-click into to run the whole
app — no Python, no Node.js, no terminal. Under the hood it is the same FastAPI
backend serving the same built frontend, bundled with
[PyInstaller](https://pyinstaller.org/); the browser is just how it shows its
UI, the way many desktop apps embed a web view.

The output is a **folder**, not a single `.exe` — `Lapus.exe` plus its support
files sit together in `packaging\dist\Lapus\`. That is normal for apps this
size (the same shape as a portable 7-Zip or VS Code install): copy or zip the
*whole folder*, and double-clicking the `.exe` inside it is still the entire
"run it" experience for whoever receives it.

This has to be **built on a Windows machine** — PyInstaller bundles a real
Windows binary and does not cross-compile from Linux or Mac. The steps below
are a one-time setup on whichever Windows machine does the building; the
resulting folder then runs on any similar Windows machine with no further
setup.

## What has actually been verified

The packaging mechanics were run end-to-end as a **Linux** build of this same
spec file, against the current code. That run confirmed:

- the build completes and produces a **52 MB** app folder,
- the built frontend and the section contract (`config/spec_sections.json`)
  are really inside the bundle, and the backend serves both UI and API from
  one port,
- the packaged app runs with the environment **stripped entirely**
  (`env -i` — no `PATH`, no Python), so nothing is quietly borrowed from the
  build machine,
- a full workflow through the packaged binary — search, open a spec, propose a
  change, submit, approve — works, and the approved value then renders as an
  overlay with the source value intact,
- after all of that, `Spec_Stage.db` was **byte-identical** to the pristine
  copy (same MD5), and the only files written were `lapus.db` and its WAL.

Treat this document as unverified only on the **Windows-specific** details,
which can only be confirmed on real Windows: the exe launching cleanly, and
Windows Defender / SmartScreen's reaction to an unsigned binary.

**Leave time for the first Windows build.** It is the one step that has never
run on Windows, so budget an afternoon rather than the evening before a
presentation.

## One-time build machine setup

1. **Git** — https://git-scm.com/download/win
2. **Python 3.11+** — https://www.python.org/downloads/ (tick "Add python.exe
   to PATH" during install)
3. **Node.js 20+** — https://nodejs.org/ (LTS)

## Build it

```
git clone https://github.com/ipalmer100/Lapus.git
cd Lapus
packaging\build_windows_exe.bat
```

The script checks that Git, Node and Python 3.11+ are present — stopping with
a list of what is missing and where to get it, rather than failing halfway
through with a confusing error — and then:

1. runs `npm install` + `npm run build` in `frontend/`, producing `frontend/dist`;
2. creates an isolated Python environment at `packaging\.build-venv` and
   installs the backend plus PyInstaller into it (keeping this off your system
   Python entirely);
3. runs PyInstaller against `packaging/lapus.spec`, bundling the backend, the
   built frontend and the section contract into one app folder.

Takes a few minutes. When it finishes, **`packaging\dist\Lapus\`** is the whole
app.

### If the script misbehaves

The `.bat` cannot run in the Linux environment this repo is developed in, so
unlike the rest of the build it has not been executed end-to-end. If it fails
in a way that looks like the script rather than your machine, these are the
exact commands it runs — do them in order from the repo root for the same
result:

```
cd frontend
npm install
npm run build
cd ..

py -3 -m venv packaging\.build-venv
packaging\.build-venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e "backend[build]"

python -m PyInstaller --clean --noconfirm --distpath packaging\dist --workpath packaging\build packaging\lapus.spec
```

If `py` is not recognised, use `python` in its place.

## Running it

Double-click `Lapus.exe` — inside the `Lapus` folder; moving the exe out on its
own will not work, it needs its sibling `_internal` folder. A console window
opens (intentionally — it shows which specification database was found and
whether the parser-owned data is protected, and it is how you stop the app) and
your default browser opens to the app.

Double-clicking the exe again while it is already running just points your
browser at the running instance rather than failing to bind the port.

### Where it looks for the specification database

In order:

1. `LAPUS_DATABASE_URL`, if set
2. `Spec_Stage.db` in the folder Lapus is run from
3. `Desktop\Specs\Spec_Stage.db` — the parser's own default output location
4. `Desktop\Spec_Stage.db`, then your home folder

If none is found, the app still starts and says so on screen and in the
console, naming the path it expected — rather than closing the window on an
error nobody can read.

**Your change requests are written elsewhere**, to
`%APPDATA%\Lapus\lapus.db`, deliberately not beside the staging database:

- the staging file may live on a read-only share,
- replacing `Spec_Stage.db` after a parser run must not disturb change requests,
- and rebuilding or replacing the app folder must not either.

Nothing in the app folder holds data. A rebuild replaces the folder in place
and asks you to re-pick nothing.

## Updating an app you already built

```
git pull
packaging\build_windows_exe.bat
```

Three things worth knowing:

- **Close the running app first.** Windows will not let PyInstaller overwrite
  `Lapus.exe` while it is running, and the failure looks like a permissions
  error rather than "the app is open".
- **Your change requests are untouched.** They live in `%APPDATA%`, not in the
  app folder.
- **Hard-refresh once after launching** (Ctrl+F5) if the UI looks unchanged —
  the browser can serve the previous version's cached page.

## Setting up a demo

Run against a **copy** of the staging database, never one being actively
rewritten by the parser. Two files:

```
C:\LapusDemo\
    Spec_Stage.db     <- a copy of the staged corpus
    Lapus\            <- the app folder from the build
```

To reset between run-throughs, delete `%APPDATA%\Lapus\lapus.db` — that clears
every change request and audit event so the workflow fills up in front of the
room rather than showing yesterday's practice. The staging database needs no
reset: Lapus cannot modify it.

To demo without the real corpus at all, generate a sample database:

```
python tools\make_demo_db.py --output C:\LapusDemo\Spec_Stage.db
```

It contains eighteen specifications with deliberately uneven data — missing
sections, a document whose source file has vanished, unmapped tables, an
ingestion error — so the empty states and the parser-health panel all have
something real to show.

### Suggested run of show

1. **Search** — type a raw material, not a spec number. Every specification
   using that web comes back. The point: this is a question nobody could answer
   before without opening documents one at a time.
2. **Open a spec** — all eleven sections, in the order they appear in the Word
   document, in business language.
3. **A gap** — open a spec with no Reporting Requirements. It says so plainly.
   Legacy documents are missing sections constantly and the tool does not
   treat that as an error.
4. **Propose a change** — a supplier on the Bill of Materials. Note that the
   current value is captured as part of the proposal, and a reason is asked for.
5. **Submit and approve** — the change request, its items and its audit trail.
6. **The payoff** — back on the specification, the approved value now shows,
   with the original Word value struck through beside it and the full decision
   one click away. Say plainly: the Word document has not been touched, and the
   next parser run cannot erase this.
7. **Parser health** — the admin view: what mapped, what did not, and the one
   legacy `.doc` that could not be staged at all.

## Known constraints of this v1 packaging

- **Unsigned binary.** Windows SmartScreen will very likely flag a fresh,
  unsigned exe from an unrecognised publisher on first run ("Windows protected
  your PC"). Click "More info" → "Run anyway". Code signing would remove this
  but needs a paid certificate.
- **One instance.** Double-clicking the exe again opens another browser tab to
  the running instance rather than a second app.
- **No system-tray mode.** The console window is the app's on/off switch.
- **Single user.** The POC runs as one configured identity
  (`DEV_USER_EMAIL`), and self-approval is enabled so the approval step can be
  demonstrated at all. See the security note in the main README before putting
  this in front of more than one person.
- **No auto-update.** Re-run the build script after pulling new code.
