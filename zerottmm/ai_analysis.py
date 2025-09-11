"""AI-powered code analysis using OpenAI API.

This module provides AI-enhanced analysis capabilities for ttmm,
allowing users to get natural language explanations and insights
about their codebases using OpenAI's GPT models.
"""

from __future__ import annotations

from typing import Dict, List, Optional


def analyze_code_with_ai(
    api_key: str,
    analysis_type: str,
    hotspots_context: List[str],
    repo_info: Dict,
    custom_prompt: Optional[str] = None,
) -> str:
    """Analyze code using OpenAI API.

    Parameters
    ----------
    api_key : str
        OpenAI API key
    analysis_type : str
        Type of analysis to perform
    hotspots_context : List[str]
        List of hotspot descriptions
    repo_info : Dict
        Repository metadata
    custom_prompt : str, optional
        Custom analysis prompt

    Returns
    -------
    str
        AI analysis result
    """
    try:
        import openai
    except ImportError:
        return ("❌ **OpenAI library not installed**\n\n"
                "Please install it with: `pip install openai`")

    # Set up OpenAI client
    client = openai.OpenAI(api_key=api_key)

    # Prepare context
    repo_context = f"""
Repository Information:
- Path: {repo_info.get('path', 'Unknown')}
- Remote URL: {repo_info.get('remote_url', 'Local repository')}
- Branch: {repo_info.get('branch', 'Unknown')}
- Commit: {repo_info.get('commit', 'Unknown')}

Top Code Hotspots (high complexity functions):
{chr(10).join(hotspots_context[:5])}
"""

    # Define analysis prompts
    analysis_prompts = {
        "Explain hotspots": (
            "Analyze the code hotspots listed above. Explain what makes these functions "
            "complex and suggest potential improvements or areas that might need attention. "
            "Focus on maintainability and potential refactoring opportunities."
        ),
        "Summarize architecture": (
            "Based on the hotspots and repository information, provide a high-level "
            "architectural summary of this codebase. Identify the main components, "
            "patterns, and overall structure."
        ),
        "Identify design patterns": (
            "Analyze the code hotspots and identify any design patterns being used. "
            "Comment on the appropriateness of these patterns and suggest alternatives "
            "if beneficial."
        ),
        "Find potential issues": (
            "Review the code hotspots for potential issues like performance bottlenecks, "
            "security concerns, maintainability problems, or technical debt. Provide "
            "specific recommendations."
        ),
        "Custom analysis": custom_prompt or "Provide a general analysis of the codebase.",
    }

    prompt = analysis_prompts.get(analysis_type, analysis_prompts["Custom analysis"])

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior software engineer helping to analyze a Python "
                        "codebase. Provide clear, actionable insights based on the code "
                        "metrics and hotspots provided. Be concise but thorough."
                    )
                },
                {
                    "role": "user",
                    "content": f"{repo_context}\n\nAnalysis Request: {prompt}"
                }
            ],
            max_tokens=1000,
            temperature=0.3,
        )

        return response.choices[0].message.content or "No analysis generated."

    except openai.OpenAIError as e:
        return f"❌ **OpenAI API Error**: {str(e)}"
    except Exception as e:
        return f"❌ **Analysis Error**: {str(e)}"


def test_openai_connection(api_key: str) -> tuple[bool, str]:
    """Test if OpenAI API key is valid.

    Parameters
    ----------
    api_key : str
        OpenAI API key to test

    Returns
    -------
    tuple[bool, str]
        (success, message)
    """
    try:
        import openai
    except ImportError:
        return False, "OpenAI library not installed"

    try:
        client = openai.OpenAI(api_key=api_key)
        # Make a minimal API call to test the key
        client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=5
        )
        return True, "API key is valid"
    except openai.AuthenticationError:
        return False, "Invalid API key"
    except openai.OpenAIError as e:
        return False, f"OpenAI API error: {str(e)}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"
