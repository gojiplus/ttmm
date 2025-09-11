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
import tempfile
import traceback

import streamlit as st

from ttmm import index as ttmm_index
from ttmm import store as ttmm_store
from ttmm import search as ttmm_search
from ttmm import gitingest
from ttmm import ai_analysis


st.set_page_config(page_title="TTMM Assistant", layout="wide")
st.title("🧠 TTMM Code Reading Assistant")
st.markdown("*Analyze Python codebases from local paths, Git URLs, or GitIngest links*")

# Input method selection
input_type = st.radio(
    "Choose input method:",
    ["Local Path", "Git URL", "GitIngest URL"],
    horizontal=True
)

if input_type == "Local Path":
    repo_input = st.text_input("Local repository path", value=".", key="local_path")
    st.caption("Path to a local Python repository")
elif input_type == "Git URL":
    repo_input = st.text_input(
        "Git repository URL",
        placeholder="https://github.com/user/repo.git",
        key="git_url"
    )
    st.caption("Direct link to a Git repository (GitHub, GitLab, Bitbucket)")
else:  # GitIngest URL
    repo_input = st.text_input(
        "GitIngest URL",
        placeholder="https://gitingest.com/?url=https://github.com/user/repo&subpath=src",
        key="gitingest_url"
    )
    st.caption("GitIngest link with optional subpath parameter")

# Store the actual repo path after processing
if "current_repo_path" not in st.session_state:
    st.session_state.current_repo_path = None
if "temp_repos" not in st.session_state:
    st.session_state.temp_repos = []

if st.button("Index repository"):
    if not repo_input.strip():
        st.warning("Please enter a repository path or URL.")
    else:
        try:
            with st.spinner("Fetching and indexing repository..."):
                # Resolve the repository path
                if input_type == "Local Path":
                    if os.path.exists(repo_input):
                        actual_repo_path = os.path.abspath(repo_input)
                    else:
                        st.error(f"Local path does not exist: {repo_input}")
                        st.stop()
                else:
                    # Remote repository - fetch it
                    actual_repo_path = gitingest.fetch_repository(repo_input)
                    if actual_repo_path is None:
                        st.error(f"Failed to fetch repository: {repo_input}")
                        st.stop()
                    # Track temp repos for cleanup
                    if actual_repo_path.startswith(tempfile.gettempdir()):
                        st.session_state.temp_repos.append(actual_repo_path)

                # Index the repository
                ttmm_index.index_repo(actual_repo_path)
                st.session_state.current_repo_path = actual_repo_path

                # Show success message with repo info
                if input_type != "Local Path":
                    repo_info = gitingest.get_repo_info(actual_repo_path)
                    if repo_info.get('remote_url'):
                        st.success(f"✅ Indexed remote repository: {repo_info['remote_url']}")
                        if repo_info.get('commit'):
                            commit_info = f"📝 Commit: {repo_info['commit']}"
                            branch_info = f"Branch: {repo_info.get('branch', 'unknown')}"
                            st.info(f"{commit_info} | {branch_info}")
                    else:
                        st.success(f"✅ Indexed repository: {repo_input}")
                else:
                    st.success(f"✅ Indexed local repository: {repo_input}")

        except Exception as e:
            st.error(f"Indexing failed: {e}")
            st.text(traceback.format_exc())

st.markdown("---")

st.subheader("Hotspots")
hotspot_limit = st.slider("Number of hotspots", min_value=5, max_value=50, value=15)
if st.button("Show hotspots"):
    if st.session_state.current_repo_path is None:
        st.warning("Please index a repository first.")
    else:
        try:
            conn = ttmm_store.connect(st.session_state.current_repo_path)
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

# AI-Enhanced Analysis Section
st.subheader("🤖 AI-Enhanced Analysis")
with st.expander("OpenAI Integration (Optional)", expanded=False):
    st.markdown("**Enhance your code analysis with AI-powered insights**")

    openai_key = st.text_input(
        "OpenAI API Key",
        type="password",
        help="Enter your OpenAI API key to get AI-powered code analysis and explanations"
    )

    if openai_key:
        # Test the API key
        is_valid, message = ai_analysis.test_openai_connection(openai_key)
        if is_valid:
            st.success("✅ OpenAI API key configured and validated")
        else:
            st.error(f"❌ API key validation failed: {message}")
            openai_key = None  # Disable further processing

        ai_query_type = st.selectbox(
            "Analysis Type",
            [
                "Explain hotspots",
                "Summarize architecture",
                "Identify design patterns",
                "Find potential issues",
                "Custom analysis"
            ]
        )

        custom_prompt = None
        if ai_query_type == "Custom analysis":
            custom_prompt = st.text_area(
                "Custom Analysis Request",
                placeholder="e.g., 'Explain the main data flow in this codebase' or "
                            "'What are the key security considerations?'"
            )

        if st.button("🚀 Run AI Analysis") and openai_key:
            if st.session_state.current_repo_path is None:
                st.warning("Please index a repository first.")
            else:
                try:
                    with st.spinner("Running AI analysis..."):
                        # Get top hotspots for context
                        conn = ttmm_store.connect(st.session_state.current_repo_path)
                        hotspots = ttmm_store.get_hotspots(conn, limit=10)
                        ttmm_store.close(conn)

                        # Prepare context for AI
                        hotspot_context = []
                        for row in hotspots[:5]:
                            entry = f"- {row['qualname']} ({row['file_path']}:{row['lineno']})"
                            entry += f" - complexity: {row['complexity']:.1f}"
                            if row.get('churn'):
                                entry += f", churn: {row['churn']:.3f}"
                            hotspot_context.append(entry)

                        repo_info = gitingest.get_repo_info(st.session_state.current_repo_path)
                        
                        # Get custom prompt if applicable
                        custom_query = custom_prompt if ai_query_type == "Custom analysis" else None

                        # Run AI analysis
                        analysis_result = ai_analysis.analyze_code_with_ai(
                            api_key=openai_key,
                            analysis_type=ai_query_type,
                            hotspots_context=hotspot_context,
                            repo_info=repo_info,
                            custom_prompt=custom_query
                        )

                        # Display results
                        st.markdown("### 🤖 AI Analysis Results")
                        st.markdown(analysis_result)

                except Exception as e:
                    st.error(f"AI analysis failed: {e}")
                    st.text(traceback.format_exc())
    else:
        st.info("💡 Add your OpenAI API key above to unlock AI-powered code analysis")

st.markdown("---")

st.subheader("🔍 Keyword Search")
query = st.text_input("Enter keywords or a question", value="")
topk = st.slider("Results", min_value=3, max_value=20, value=5)
if st.button("Answer"):
    if not query.strip():
        st.warning("Please enter a question.")
    else:
        if st.session_state.current_repo_path is None:
            st.warning("Please index a repository first.")
        else:
            try:
                results = ttmm_search.answer_question(
                    st.session_state.current_repo_path, query, top=topk, include_scores=True
                )
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
                    st.info("No relevant symbols found; try a different query or "
                            "re‑index the repository.")
            except Exception as e:
                st.error(f"Search failed: {e}")
                st.text(traceback.format_exc())

# Footer with cleanup info
st.markdown("---")
st.markdown("### 🗂️ Session Info")
if st.session_state.current_repo_path:
    if st.session_state.current_repo_path.startswith(tempfile.gettempdir()):
        st.info(f"📁 **Temporary repository:** {st.session_state.current_repo_path}")
        st.caption("This repository was downloaded temporarily and will be "
                   "cleaned up when you close the session.")
    else:
        st.info(f"📁 **Local repository:** {st.session_state.current_repo_path}")

    if st.button("🗑️ Clear Session"):
        # Cleanup temp repositories
        for temp_path in st.session_state.temp_repos:
            try:
                gitingest.cleanup_temp_repo(temp_path)
            except Exception:
                pass
        st.session_state.current_repo_path = None
        st.session_state.temp_repos = []
        st.rerun()
else:
    st.info("No repository currently indexed")
