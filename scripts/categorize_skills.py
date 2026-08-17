#!/usr/bin/env python3
"""
Regenerates the "All skills" section of README.md from the live contents of
skills/*/SKILL.md — self-contained, no dependency on anything outside this repo.

Usage:
    uv run python scripts/categorize_skills.py            # print categorized markdown
    uv run python scripts/categorize_skills.py --check     # exit 1 if any skill is uncategorized

Run this after adding or removing a skill folder, then paste the output between
"## All skills (N)" and "## Bulk-installed plugins" in README.md (update the
count in the heading too).
"""
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(REPO_ROOT, "skills")

# Skills whose SKILL.md doesn't tell you where they came from — filled in by hand
# when they were added. Everything not listed here defaults to
# K-Dense-AI/claude-scientific-skills, the source of the 2026-08-16 bulk install.
SOURCE_OVERRIDES = {
    "ste-writing": "loose file, ~/Downloads (2026-08-08)",
    "task-observer": "rebelytics/one-skill-to-rule-them-all (submodule)",
    "finding-duplicate-functions": "obra/superpowers-lab",
    "mcp-cli": "obra/superpowers-lab",
    "using-tmux-for-interactive-commands": "obra/superpowers-lab",
    "windows-vm": "obra/superpowers-lab",
    "ffuf-web-fuzzing": "jthack/ffuf_claude_skill",
    "d3-viz": "chrisvoncsefalvay/claude-d3js-skill",
    "gstack": "garrytan/gstack",
    "video-use": "browser-use/video-use",
    "find-skills": "vercel-labs/skills (find-skills)",
    "emil-design-eng": "emilkowalski/skills (emil-design-eng)",
    "which-skill": "written for this repo, 2026-08-16",
}
# humanizer used to be a loose ~/Downloads file of unknown origin; its real source
# turned out to be blader/humanizer (confirmed byte-identical 2026-08-16), so it's
# now tracked as the humanizer@humanizer plugin instead of a raw skill here.
DEFAULT_SOURCE = "K-Dense-AI/claude-scientific-skills"

# One category per skill. A skill not listed here is reported as uncategorized
# (see --check) rather than silently dropped from the README.
CATEGORIES = {
    "Core & Meta Skills": [
        "ste-writing", "task-observer", "autoskill",
    ],
    "Developer & Agent Tooling": [
        "finding-duplicate-functions", "mcp-cli", "using-tmux-for-interactive-commands",
        "windows-vm", "pi-agent", "get-available-resources", "gstack", "find-skills",
        "which-skill",
    ],
    "Security & Pentesting": [
        "ffuf-web-fuzzing",
    ],
    "Documents, Slides & Reports": [
        "docx", "pdf", "pptx", "pptx-posters", "latex-posters", "xlsx", "scientific-slides",
        "markitdown", "venue-templates", "liteparse",
    ],
    "Data Visualization & Graphics": [
        "d3-viz", "matplotlib", "seaborn", "scientific-visualization", "networkx",
        "generate-image", "infographics", "scientific-schematics",
    ],
    "Research, Literature & Writing": [
        "citation-management", "literature-review", "paper-lookup", "paperclip", "paperzilla",
        "peer-review", "research-grants", "research-lookup", "scholar-evaluation",
        "scientific-writing", "bgpt-paper-search", "database-lookup", "exa-search",
        "parallel-web", "open-notebook", "markdown-mermaid-writing", "market-research-reports",
        "usfiscaldata", "pyzotero",
    ],
    "Statistics, Experimental Design & Reasoning": [
        "analytical-method-validation", "experimental-design", "exploratory-data-analysis",
        "hypogenic", "hypothesis-generation", "pymc", "scikit-survival", "statistical-analysis",
        "statistical-power", "statsmodels", "uncertainty-and-units", "relsa-severity-assessment",
        "simpy", "pymoo", "scientific-critical-thinking", "scientific-brainstorming",
        "consciousness-council", "what-if-oracle", "dhdna-profiler",
    ],
    "Bioinformatics & Genomics": [
        "adaptyv", "anndata", "arboreto", "bids", "biopython", "bioservices", "bulk-rnaseq",
        "cellxgene-census", "deepspot-m", "deeptools", "depmap", "dnanexus-integration", "esm",
        "etetoolkit", "flowio", "genomic-coordinates", "genomic-intelligence", "geniml", "gtars",
        "gget", "histolab", "imaging-data-commons", "lamindb", "latchbio-integration", "nextflow",
        "omero-integration", "onekgpd", "ontology-term-resolution", "pacsomatic",
        "pathogen-variant-surveillance", "pathway-enrichment", "phylogenetics", "polars-bio",
        "primekg", "pydeseq2", "pysam", "scanpy", "scikit-bio", "scvelo", "scvi-tools",
        "tiledbvcf", "ncats-arax", "molecular-dynamics", "cobrapy", "neuropixels-analysis",
        "glycoengineering", "neurokit2", "pathml",
    ],
    "Chemistry, Drug Discovery & Materials": [
        "datamol", "deepchem", "medchem", "molfeat", "pymatgen", "rdkit", "rowan", "tamarind",
        "torchdrug", "pytdc", "diffdock", "matchms", "pyopenms",
    ],
    "Machine Learning & Compute Infrastructure": [
        "arbor", "aeon", "hugging-science", "modal", "optimize-for-gpu", "pufferlib",
        "pytorch-lightning", "scikit-learn", "shap", "stable-baselines3", "timesfm-forecasting",
        "torch-geometric", "transformers", "umap-learn", "dask", "vaex", "polars", "zarr-python",
    ],
    "Quantum Computing & Physics": [
        "cirq", "qiskit", "qutip", "pennylane", "astropy", "fluidsim", "openpiv", "sympy",
        "matlab",
    ],
    "Clinical & Healthcare": [
        "clinical-decision-support", "clinical-reports", "treatment-plans", "pkpd-modeling",
        "iso-standards-readiness", "pyhealth", "pydicom",
    ],
    "Lab Operations & Automation": [
        "ginkgo-cloud-lab", "opentrons-integration", "pylabrobot", "lab-hardware-cad",
        "labarchive-integration", "protocolsio-integration", "benchling-integration",
    ],
    "Geospatial & Earth Science": [
        "geomaster", "geopandas",
    ],
    "Media & Content Creation": [
        "video-use",
    ],
    "Design & Frontend": [
        "emil-design-eng",
    ],
}


def extract_description(skill_md_path):
    lines = open(skill_md_path, encoding="utf-8", errors="replace").read().splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^description:\s*(.*)$", line)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest in (">", "|", ">-", "|-"):
            block = []
            for cont in lines[i + 1:]:
                if cont.startswith((" ", "\t")) and cont.strip():
                    block.append(cont.strip())
                elif not cont.strip():
                    continue
                else:
                    break
            desc = " ".join(block)
        else:
            desc = rest.strip('"')
        return desc
    return ""


GSTACK_ROOT = os.path.realpath(os.path.join(SKILLS_DIR, "gstack"))
# Two of gstack's ./setup outputs are real materialized files, not symlinks into the
# gstack/ submodule, so the realpath check below doesn't catch them - same reasoning
# as the symlinked ones: facets of gstack, not independent skills.
GSTACK_EXTRA_FILES = {"_gstack-command", "connect-chrome"}


def load_skills():
    skills = {}
    for name in sorted(os.listdir(SKILLS_DIR), key=str.lower):
        skill_md = os.path.join(SKILLS_DIR, name, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        if name in GSTACK_EXTRA_FILES:
            continue
        if name != "gstack" and os.path.realpath(skill_md).startswith(GSTACK_ROOT + os.sep):
            # gstack's own ./setup symlinks each of its ~55 sub-skills to a sibling
            # directory here (browse/, qa/, ship/, ...) so Claude Code can discover
            # them individually. They're facets of the single `gstack` entry, not
            # independent skills with their own provenance — skip them so this list
            # doesn't balloon into 55 near-duplicate rows every time gstack updates.
            continue
        desc = extract_description(skill_md).replace("\t", " ").replace("|", "\\|").strip()
        if len(desc) > 130:
            desc = desc[:127] + "..."
        source = SOURCE_OVERRIDES.get(name, DEFAULT_SOURCE)
        skills[name] = (source, desc)
    return skills


def anchor(cat):
    # GitHub's real heading-anchor algorithm: lowercase, strip anything that isn't
    # a letter/digit/space/hyphen, turn spaces into hyphens. It does NOT collapse
    # consecutive hyphens (e.g. "X & Y" -> "x--y") - do not "clean that up".
    return re.sub(r"[^a-z0-9\- ]", "", cat.lower()).replace(" ", "-")


def main():
    skills = load_skills()
    assigned = [n for names in CATEGORIES.values() for n in names]
    assigned_set = set(assigned)
    all_names = set(skills.keys())

    missing = sorted(all_names - assigned_set)
    dupes = sorted({n for n in assigned_set if assigned.count(n) > 1})
    ghosts = sorted(assigned_set - all_names)  # categorized but no longer exist

    if missing or dupes or ghosts:
        print(f"WARNING: {len(missing)} uncategorized, {len(dupes)} duplicated, "
              f"{len(ghosts)} categorized-but-missing skills:", file=sys.stderr)
        if missing:
            print("  uncategorized (add to CATEGORIES in this script):", missing, file=sys.stderr)
        if dupes:
            print("  in more than one category:", dupes, file=sys.stderr)
        if ghosts:
            print("  categorized but no longer in skills/ (remove from CATEGORIES):", ghosts,
                  file=sys.stderr)
        if "--check" in sys.argv:
            sys.exit(1)

    toc = [f"- [{cat}](#{anchor(cat)}) ({len(names)})" for cat, names in CATEGORIES.items()]
    body = []
    for cat, names in CATEGORIES.items():
        present = [n for n in names if n in skills]
        body.append(f"### {cat}\n")
        body.append("| Skill | Source | Description |")
        body.append("|---|---|---|")
        for name in sorted(present, key=str.lower):
            source, desc = skills[name]
            body.append(f"| `{name}` | {source} | {desc} |")
        body.append("")

    if "--check" not in sys.argv:
        print(f"## All skills ({len(all_names)})\n")
        print("\n".join(toc))
        print()
        print("\n".join(body))


if __name__ == "__main__":
    main()
