# Import dotenv to load the .env file
from dotenv import load_dotenv
# Import os to read environment variables (stuff in .env -- the file you hide secrets in)
import os
from openai import OpenAI

''' Initialise OpenAI client '''
load_dotenv()
key = os.getenv("OPENAI_API_KEY")
if not key:
    raise EnvironmentError("OPENAI_API_KEY is not set in environment variables. Check .env")

client = OpenAI(api_key=key)

''' Job rating function'''
def rate_job(title: str, description: str, company: str) -> int:
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

    # Cast the response into an int type
    # TODO: error handling and graceful failure state needed here.
    return int(response.choices[0].message.content.strip())



''' Testing '''
if __name__ == "__main__":
    # This will only run if you run this file directly
    score = rate_job(
        title="Tree Planter",
        description="We plant trees to restore forests and improve biodiversity.",
        company="EcoRegen"
    )

    print("Green Score:", score)
