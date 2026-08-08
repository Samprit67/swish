# 🏀 Swish

**Estimate an NBA player's trade value from his stats and his contract.**

Type in a name. Swish pulls the player's career numbers from Basketball-Reference,
projects his production forward with an age curve, prices those wins in dollars,
subtracts what he's owed, and tells you what the asset is actually worth — on a
scale you can read as draft picks.

_Full README lands with the first release. Work in progress._

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

swish value "Luka Doncic"      # full breakdown in the terminal
swish serve                    # dashboard at http://127.0.0.1:8770
```

## License

MIT — see [LICENSE](LICENSE).
