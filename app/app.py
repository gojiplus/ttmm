"""Streamlit app for the ttmm code reading assistant.

This UI allows you to index a Python repository, explore hotspots and
ask natural language questions to find relevant functions or methods.

To run locally:

```
streamlit run app/app.py
```

If deploying on Streamlit Community Cloud, set the working directory
to the repository root and the main file to ``app/app.py``.
"""

from __future__ import annotations

import os
import traceback

import streamlit as st

from ttmm import index as ttmm_index
from ttmm import store as ttmm_store
from ttmm import search as ttmm_search


st.set_page_config(page_title="TTMM Assistant", layout="wide")
st.title("🧠 TTMM Code Reading Assistant")

# Repository path input
repo_path = st.text_input("Repository path", value=".")

if st.button("Index repository"):
    try:
        ttmm_index.index_repo(repo_path)
        st.success(f"Indexed repository at {repo_path}")
    except Exception as e:
        st.error(f"Indexing failed: {e}")
        st.text(traceback.format_exc())

st.markdown("---")

st.subheader("Hotspots")
hotspot_limit = st.slider("Number of hotspots", min_value=5, max_value=50, value=15)
if st.button("Show hotspots"):
    try:
        conn = ttmm_store.connect(repo_path)
        rows = ttmm_store.get_hotspots(conn, limit=hotspot_limit)
        ttmm_store.close(conn)
        if rows:
            # Prepare display data
            table = []
            for row in rows:
                score = row["complexity"] * (1.0 + (row["churn"] or 0) ** 0.5)
                table.append({
                    "Symbol": row["qualname"],
                    "File": f"{row['file_path']}:{row['lineno']}",
                    "Complexity": f"{row['complexity']:.1f}",
                    "Churn": f"{row['churn']:.3f}",
                    "Score": f"{score:.2f}",
                })
            st.dataframe(table)
        else:
            st.info("No hotspot data available; please index the repository first.")
    except Exception as e:
        st.error(f"Failed to load hotspots: {e}")

st.markdown("---")

st.subheader("Ask a question")
query = st.text_input("Enter keywords or a question", value="")
topk = st.slider("Results", min_value=3, max_value=20, value=5)
if st.button("Answer"):
    if not query.strip():
        st.warning("Please enter a question.")
    else:
        try:
            results = ttmm_search.answer_question(repo_path, query, top=topk, include_scores=True)
            if results:
                table = []
                for qualname, path, lineno, score in results:
                    table.append({
                        "Symbol": qualname,
                        "File": f"{path}:{lineno}",
                        "Score": f"{score:.2f}",
                    })
                st.dataframe(table)
            else:
                st.info("No relevant symbols found; try a different query or re‑index the repository.")
        except Exception as e:
            st.error(f"Search failed: {e}")
            st.text(traceback.format_exc())
