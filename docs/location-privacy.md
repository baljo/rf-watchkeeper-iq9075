# Observer location privacy

Describe the installation as **Vaasa/Korsholm region, Finland**. Do not publish residential addresses, exact observer/GPS positions, private map centres or satellite observer metadata in source, examples, logs, patches, service snapshots or validation evidence.

`config/examples/ais-config.example.json` and `config/examples/meteor-config.example.json` contain clearly labelled approximate example coordinates (63.08, 21.57), around Vaasa city centre and about six kilometres from the installation. They are not reception/planning calibration. For a new installation, copy the examples to ignored `ais-config.json` and `meteor-config.json`, then enter private observer settings locally. Existing EVK configuration must be preserved. Public dashboard observer/map centres and test fixtures use the same example; this export must not overwrite the live private dashboard.

The public runtime filenames are deliberately absent from Git and ignored. Ignore rules do not sanitize already tracked files, HTML, patches or evidence: review every export, including bare numeric pairs, rounded/truncated variants and addresses. Do not export a private configuration snapshot under another filename. Public broadcast vessel/met-hydro station positions and regional coastline geometry are distinct from the receiver location and are retained with their existing provenance.

## Exposure found on 5 October 2026

GitHub API inspection confirms the repository is currently **private**, with no issues, releases, tags, Actions artifacts, wiki or Pages site. This audit establishes committed exposure to authorized repository readers and a risk if made public; it does not establish prior public accessibility. The initial GitHub-published commit `c59dc08f9b749ed1825703c8b50734762219eeb8` contained precise installation coordinates in seven files: `ais-config.json`, `meteor-config.json`, `dashboard.html` (observer and two map centres), `test_ais_validation.py`, `docs/hardware.md`, `docs/evidence/documentation-inspection.json` (two observer objects), and `docs/evidence/meteor-retention.patch` (old/new config snapshots).

The cleanup replaces these values, converts configurations to examples and labels sanitized historical evidence. The private live EVK coordinates and dashboard are unchanged. Sanitized evidence is no longer a byte-exact private snapshot; old publication hashes describe the original export, not the corrected files.

**The precise coordinates remain retrievable from the initial published Git commit and from this change's parent/diff. A normal cleanup commit does not erase historical exposure.** History was not rewritten. This is the least disruptive remedy, not complete removal. If historical removal is required, a separately scoped history rewrite and review of GitHub cached views, forks and clones is needed; a force push alone cannot establish removal from copies.

The audit covered all tracked files and every commit reachable from fetched branches/tags, numeric/context searches, configs, docs, patches, retained evidence, service snapshots and static map data. No residential address was found. [Audit evidence](evidence/coordinate-privacy-audit.json) records file/history scope without repeating the private pair. Deleted refs, third-party copies and caches are outside verification.
