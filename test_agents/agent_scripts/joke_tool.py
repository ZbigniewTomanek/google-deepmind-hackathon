#!/usr/bin/env python3
"""Joke generation tool for the joke subagent."""

import random

from pydantic import BaseModel, Field

from open_agent_compiler.runtime import ScriptTool


class JokeInput(BaseModel):
    topic: str = Field(default="programming", description="Topic for the joke")
    style: str = Field(default="pun", description="Style: pun, one-liner, knock-knock, observational")


class JokeOutput(BaseModel):
    joke: str
    topic: str
    style: str


_JOKES = {
    "pun": [
        "Why do {topic} experts never get lost? Because they always follow the right path.",
        "I told my friend a {topic} joke. They didn't get it — must be a runtime error.",
        "What's a {topic} enthusiast's favorite music? Algo-rhythm.",
    ],
    "one-liner": [
        "I asked AI about {topic} and it said 'that's above my pay grade' — which is $0.",
        "The best thing about {topic}? It's never boring... unless you're debugging it.",
        "They say {topic} is the future. The future is now. And it's full of bugs.",
    ],
    "knock-knock": [
        "Knock knock. Who's there? {topic}. {topic} who? {topic} your mind, this joke writes itself!",
        "Knock knock. Who's there? An expert on {topic}. An expert who? Exactly — nobody knows.",
    ],
    "observational": [
        "Have you noticed how everyone talks about {topic} like they understand it? Narrator: they didn't.",
        "The thing about {topic} is that the more you know, the more you realize you need a nap.",
        "People say {topic} will change the world. So will a good sandwich, but nobody hypes that.",
    ],
}


class JokeTool(ScriptTool[JokeInput, JokeOutput]):
    name = "joke-tool"
    description = "Generate a joke on a given topic and style"

    def execute(self, input: JokeInput) -> JokeOutput:
        style = input.style if input.style in _JOKES else "pun"
        template = random.choice(_JOKES[style])
        joke = template.format(topic=input.topic)
        return JokeOutput(joke=joke, topic=input.topic, style=style)


if __name__ == "__main__":
    JokeTool.run()
