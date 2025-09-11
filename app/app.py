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

from zerottmm import index as ttmm_index
from zerottmm import store as ttmm_store
from zerottmm import search as ttmm_search
from zerottmm import gitingest
from zerottmm import ai_analysis


def _show_repository_summary(repo_path: str) -> None:
    """Display an automatic repository summary."""
    import math
    try:
        # Get repository basic info
        repo_info = gitingest.get_repo_info(repo_path)

        # Get database statistics
        conn = ttmm_store.connect(repo_path)
        cur = conn.cursor()

        # Count files, symbols, and get top complexity functions
        cur.execute("SELECT COUNT(*) FROM files")
        file_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM symbols")
        symbol_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM symbols WHERE type = 'function'")
        function_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM symbols WHERE type = 'method'")
        method_count = cur.fetchone()[0]

        # Get top 3 hotspots for preview
        hotspots = ttmm_store.get_hotspots(conn, limit=3)
        ttmm_store.close(conn)

        # Display basic stats
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📁 Python Files", file_count)
        with col2:
            st.metric("🔧 Functions", function_count)
        with col3:
            st.metric("⚙️ Methods", method_count)
        with col4:
            st.metric("📊 Total Symbols", symbol_count)

        # Repository info
        if repo_info.get('remote_url'):
            st.markdown(f"**Repository:** {repo_info['remote_url']}")
            if repo_info.get('branch') and repo_info.get('commit'):
                branch_commit = f"**Branch:** {repo_info['branch']} | "
                branch_commit += f"**Commit:** {repo_info['commit']}"
                st.markdown(branch_commit)

        # Top complexity preview
        if hotspots:
            st.markdown("**🔥 Top Complexity Hotspots:**")
            for i, row in enumerate(hotspots, 1):
                score = row["complexity"] * (1.0 + math.sqrt(row["churn"] or 0))
                hotspot_info = f"{i}. `{row['qualname']}` "
                hotspot_info += f"({row['file_path']}:{row['lineno']}) - "
                hotspot_info += f"complexity: {row['complexity']:.1f}, score: {score:.1f}"
                st.markdown(hotspot_info)

        # Basic analysis without OpenAI
        st.markdown("**📋 Quick Analysis:**")

        # Function vs method ratio analysis
        if symbol_count > 0:
            method_ratio = method_count / symbol_count
            if method_ratio > 0.6:
                analysis = "• **Object-oriented codebase** - High proportion of class methods"
                st.markdown(analysis)
            elif method_ratio < 0.3:
                st.markdown("• **Functional codebase** - Mostly standalone functions")
            else:
                analysis = "• **Mixed paradigm codebase** - Balance of functions and methods"
                st.markdown(analysis)

        # Complexity analysis
        if hotspots:
            avg_complexity = sum(row["complexity"] for row in hotspots) / len(hotspots)
            if avg_complexity > 10:
                analysis = "• **High complexity detected** - Consider refactoring top hotspots"
                st.markdown(analysis)
            elif avg_complexity > 5:
                analysis = "• **Moderate complexity** - Some functions may benefit from "
                analysis += "simplification"
                st.markdown(analysis)
            else:
                st.markdown("• **Low complexity** - Well-structured, readable code")

        # File organization
        if file_count > 20:
            analysis = "• **Large codebase** - Consider using call graph navigation for "
            analysis += "exploration"
            st.markdown(analysis)
        elif file_count > 5:
            st.markdown("• **Medium codebase** - Good size for comprehensive analysis")
        else:
            st.markdown("• **Small codebase** - Easy to navigate and understand")

    except Exception as e:
        st.error(f"Failed to generate summary: {e}")
        st.text(traceback.format_exc())


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

                # Generate and show repository summary
                _show_repository_summary(actual_repo_path)

        except Exception as e:
            st.error(f"Indexing failed: {e}")
            st.text(traceback.format_exc())

st.markdown("---")

# Repository Summary Section
if st.session_state.current_repo_path:
    st.subheader("📊 Repository Summary")
    if st.button("🔄 Refresh Summary"):
        _show_repository_summary(st.session_state.current_repo_path)
    else:
        # Show summary for already indexed repo
        _show_repository_summary(st.session_state.current_repo_path)

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
    elif "not installed" in message.lower():
        st.warning("⚠️ OpenAI library not installed. Install with: `pip install openai`")
        st.info("💡 You can still use the basic repository analysis features without OpenAI")
        openai_key = None  # Disable further processing
    else:
        st.error(f"❌ API key validation failed: {message}")
        openai_key = None  # Disable further processing

    ai_query_type = None
    custom_prompt = None

    if openai_key:
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
                        try:
                            if row['churn'] is not None:
                                entry += f", churn: {row['churn']:.3f}"
                        except (KeyError, IndexError):
                            pass
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
