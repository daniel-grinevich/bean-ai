from pydantic_ai import Agent

from .config import settings

agent_model_str = settings.agent_model
roulette_agent = Agent(
    model_string=agent_model_str,
    deps_type=int,
    output_type=bool,
    instructions=(
        "Use the `roulette_wheel` function to see if the "
        "customer has won based on the number they provide."
    ),
)


@roulette_agent.tool
async def roulette_wheel(ctx: RunContext[int], square: int) -> str:
    """check if the square is a winner"""
    return "winner" if square == ctx.deps else "loser"


success_number = 18
result = roulette_agent.run_sync("Put my money on square eighteen", deps=success_number)
print(result.output)

result = roulette_agent.run_sync("I bet five is the winner", deps=success_number)
print(result.output)
