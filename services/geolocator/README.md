# Crop Circle Geolocator

Local, deterministic field-candidate search and reviewed aerial-image registration for Crop Circle Atlas. The worker writes versioned evidence to an external cache and never edits the canonical catalog during machine processing.

Install the lightweight development and local-service groups from the repository root:

```powershell
python -m pip install -e "services/geolocator[dev,server,stac]"
```

See `docs/GEOLOCATOR_SETUP.md` for configuration and `docs/GEOLOCATOR_EVIDENCE_RULES.md` for the mandatory review boundary.
