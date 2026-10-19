"""Logic CrewAI: Research -> Writer -> Social. Được main.py (backend) gọi."""

import os
from pathlib import Path
from typing import Callable, Optional

from dotenv import load_dotenv
from crewai import Agent, Crew, LLM, Process, Task
from crewai_tools import SerperDevTool

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini/gemini-3.1-flash-lite")


def missing_keys() -> list[str]:
    return [k for k in ("SERPER_API_KEY", "GOOGLE_API_KEY") if not os.getenv(k)]


def run_crew(
    topic: str,
    language: str = "Vietnamese",
    with_social: bool = True,
    on_task_done: Optional[Callable[[int], None]] = None,
) -> dict:
    """Chạy crew với chủ đề do người dùng nhập, trả về dict kết quả."""
    llm = LLM(model=MODEL_NAME, api_key=os.environ["GOOGLE_API_KEY"], max_tokens=2000)

    research_agent = Agent(
        role="Senior Research Analyst",
        goal="Uncover cutting-edge information and insights on any subject with comprehensive analysis",
        backstory=(
            "You are an expert researcher experienced in gathering, analyzing, and synthesizing "
            "information across domains. You quickly identify key trends, separate fact from "
            "opinion, and find reliable sources."
        ),
        verbose=True, llm=llm, tools=[SerperDevTool()],
    )
    writer_agent = Agent(
        role="Tech Content Strategist",
        goal="Craft well-structured and engaging content based on research findings",
        backstory=(
            "You are a skilled content strategist known for translating complex topics into "
            "clear and compelling narratives for a wide audience."
        ),
        verbose=True, llm=llm, allow_delegation=True,
    )
    social_agent = Agent(
        role="Social Media Strategist",
        goal="Generate engaging social media snippets based on the full article",
        backstory="A digital storyteller who crafts compelling posts to drive engagement and traffic.",
        verbose=True, llm=llm, tools=[SerperDevTool()],
    )

    lang_note = f" Write the final output in {language}."

    research_task = Task(
        description=(
            "Analyze the major {topic}, identifying key trends and technologies. "
            "Provide a detailed report on their potential impact." + lang_note
        ),
        agent=research_agent,
        expected_output="A detailed report on {topic}, including trends, emerging technologies, and their impact.",
    )
    writer_task = Task(
        description=(
            "Create an engaging blog post based on the research findings about {topic}. "
            "Tailor the content for a tech-savvy audience, ensuring clarity and interest." + lang_note
        ),
        agent=writer_agent,
        expected_output="A 4-paragraph blog post on {topic}, written clearly and engagingly for tech enthusiasts.",
    )
    social_task = Task(
        description=(
            "Summarize the blog post about {topic} into 2-3 engaging social media posts suitable "
            "for LinkedIn or Twitter. Keep the tone informative, professional, and encouraging "
            "further reading." + lang_note
        ),
        agent=social_agent,
        expected_output="A series of 2-3 well-written social posts highlighting the key insights from the blog content.",
    )

    agents = [research_agent, writer_agent]
    tasks = [research_task, writer_task]
    titles = ["Báo cáo nghiên cứu", "Bài blog"]
    if with_social:
        agents.append(social_agent)
        tasks.append(social_task)
        titles.append("Bài mạng xã hội")

    done = {"n": 0}

    def _callback(_output) -> None:
        done["n"] += 1
        if on_task_done:
            on_task_done(done["n"])

    crew = Crew(
        agents=agents, tasks=tasks, process=Process.sequential,
        verbose=True, task_callback=_callback,
    )
    result = crew.kickoff(inputs={"topic": topic})

    usage = result.token_usage
    return {
        "final": result.raw,
        "tasks": [
            {"title": titles[i], "output": t.raw}
            for i, t in enumerate(result.tasks_output)
        ],
        "tokens": {
            "total": usage.total_tokens,
            "prompt": usage.prompt_tokens,
            "completion": usage.completion_tokens,
        },
    }