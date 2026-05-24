"""
Tool-augmented agent — wraps LLM calls with tool use capability.

Agents can call tools mid-reasoning to fetch papers, search the web,
read/write workspace files. This closes the gap with AI-Researcher's
browser env and tool retrieval system.
"""
from __future__ import annotations
import json
import re
from ..core.config import LabConfig, ModelProfile
from ..providers.llm import LLMProvider
from .registry import ToolRegistry, ToolResult


TOOL_SYSTEM_PROMPT = """You are a research agent with access to tools.
When you need information, call a tool using this exact format:

<tool_call>
{{"tool": "tool_name", "args": {{"key": "value"}}}}
</tool_call>

Available tools:
{tool_list}

After receiving tool results, continue your reasoning.
You may call multiple tools in sequence.
When you have enough information, provide your final answer.
"""


class ToolAugmentedAgent:
    """
    Wraps an LLM with tool-calling capability.
    Handles the tool-call → result → continue loop.
    """

    def __init__(self, config: LabConfig, llm: LLMProvider, tools: ToolRegistry):
        self.config = config
        self.llm = llm
        self.tools = tools
        self.max_tool_calls = 8  # prevent infinite loops

    async def run(
        self,
        model: ModelProfile,
        user_prompt: str,
        system_extra: str = "",
        temperature: float = 0.5,
    ) -> str:
        """
        Run agent with tool use. Returns final text response.
        """
        tool_list = "\n".join(
            f"- {t['name']}: {t['description']}"
            for t in self.tools.list_tools()
        )
        system = TOOL_SYSTEM_PROMPT.format(tool_list=tool_list)
        if system_extra:
            system += f"\n\n{system_extra}"

        messages = [{"role": "user", "content": user_prompt}]
        call_count = 0

        while call_count < self.max_tool_calls:
            response = await self.llm.complete(
                model, messages, temperature=temperature,
                system=system, max_tokens=4096,
            )

            # Check for tool calls
            tool_calls = self._extract_tool_calls(response)
            if not tool_calls:
                return response  # No more tool calls — final answer

            # Execute tool calls and append results
            tool_results_text = []
            for call in tool_calls:
                result = await self.tools.call(call["tool"], call.get("args", {}))
                status = "✓" if result.success else "✗"
                tool_results_text.append(
                    f"<tool_result tool=\"{call['tool']}\" status=\"{status}\">\n"
                    f"{result.output if result.success else result.error}\n"
                    f"</tool_result>"
                )
                call_count += 1

            # Add assistant response + tool results to conversation
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": "\n\n".join(tool_results_text) + "\n\nContinue your analysis."
            })

        # Max calls reached — return last response
        return response

    def _extract_tool_calls(self, text: str) -> list[dict]:
        """Extract tool calls from response text."""
        calls = []
        for match in re.finditer(r'<tool_call>\s*(.*?)\s*</tool_call>', text, re.DOTALL):
            try:
                call = json.loads(match.group(1))
                if "tool" in call:
                    calls.append(call)
            except json.JSONDecodeError:
                pass
        return calls
