# Reproduction entry points. `make verify` needs no API key and no network: it recomputes
# everything that can be recomputed from the released records and fails loudly on any
# disagreement between the paper and the data.

PY ?= python3

.PHONY: help verify data tables paper clean

help:
	@echo "make verify   recompute every checkable claim (offline, no API key, ~1 min)"
	@echo "make data     regenerate the 1,200 SEW-Bench frames from the fixed seed (~30 s)"
	@echo "make tables   regenerate the paper's generated tables/figures from results/"
	@echo "make paper    build paper/asp/asp.pdf (needs a TeX distribution)"

# ---------------------------------------------------------------- verify
# Five independent checks. Each is offline and each exits non-zero on failure, so a green
# run is a claim about the artifact rather than about our diligence.
verify: data
	@echo "== 1/5  bound arithmetic: every closed-form ceiling in the paper vs data/sew/meta.json"
	$(PY) analysis/check_bounds.py
	@echo "== 2/5  corpus regeneration contract: frames byte-identical, only the 4 fixed CMP items move"
	$(PY) annotation/selftest_regen.py
	@echo "== 3/5  budget accountant invariants (offline, no API)"
	$(PY) scripts/selftest_budget.py
	@echo "== 4/5  provider-fault retry ladder (offline, no API)"
	$(PY) scripts/selftest_retry.py
	@echo "== 5/5  verdicts and tables recomputed from results/, and floats audited"
	$(PY) analysis/analyze.py
	$(PY) analysis/check_figures.py --agreement
	@echo
	@echo "all checks passed."

# The frames are not tracked; they are a pure function of the seed.
data: data/sew/frames
data/sew/frames:
	$(PY) annotation/generate_synthetic.py --out data/sew

tables:
	$(PY) analysis/make_tables.py
	$(PY) analysis/analyze.py

paper:
	cd paper/asp && latexmk -pdf asp.tex

clean:
	rm -rf __pycache__ */__pycache__ analysis/.figbaseline
	cd paper/asp && latexmk -C || true
