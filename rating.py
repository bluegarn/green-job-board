

# Mohammed, write the function that writes jobs here
#   Tip: Ask chatGPT (on the website, not in Python) what a "system prompt" is and write a system prompt for this AI -- it'll help ALOT
#      : Write a "MegaPrompts", this will help: https://www.godofprompt.ai/gpts/mega-prompt-generator
# Input: title: job title, description: job description, company: hiring company
# Output: A rating of 1 to 10 of how "green" the job is
from openai import OpenAI

client = OpenAI(api_key="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")


def rate_job(title, description, company):
    system_prompt = "You are a sustainability expert who rates how environmentally green a job is, from 1 (not green) to 10 (very green). Only return a single number."

    user_prompt = f"""
    Please rate the environmental sustainability of this job posting.

    Title: {title}
    Company: {company}

    Job Description:
    \"\"\"
    {description}
    \"\"\"

    Return just a number from 1 to 10.
    """

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0,
        max_tokens=10
    )

    return response.choices[0].message.content.strip()

# ✅ Example usage
score = rate_job(
    title="Tree Planter",
    description="We plant trees to restore forests and improve biodiversity.",
    company="EcoRegen"
)

print("Green Score:", score)
