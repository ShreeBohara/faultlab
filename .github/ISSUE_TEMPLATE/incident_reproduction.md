---
name: Incident reproduction
about: An agent did something wrong or lied about an outcome; help us reproduce it in the lab
labels: incident
---

**The workflow** (what the agent was supposed to do; which tools change state)

**What actually happened in the service** (duplicate effect, missing effect, wrong target, stale state)

**What the agent reported**

**The fault, if known** (lost reply after a write, delayed completion, stale read, transient error, duplicate delivery)

**Framework and version** (LangGraph, OpenAI Agents SDK, Claude Agent SDK, CrewAI, Pydantic AI, smolagents, MCP server)

**Can you share a minimal repro?** (a public repository link is ideal; no credentials, no customer data)
