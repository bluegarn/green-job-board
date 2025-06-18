

# Mohammed, write the function that writes jobs here
#   Tip: Ask chatGPT (on the website, not in Python) what a "system prompt" is and write a system prompt for this AI -- it'll help ALOT
#      : Write a "MegaPrompts", this will help: https://www.godofprompt.ai/gpts/mega-prompt-generator
# Input: title: job title, description: job description, company: hiring company
# Output: A rating of 1 to 10 of how "green" the job is

from openai import OpenAI

client = OpenAI(api_key="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")

job_description = "we are going to plant the trees"

prompt = f"""You're a sustainability expert. Rate this job description from 0 to 10 based on environmental sustainability.
      Only return a single number.

      Job Description:
      \"\"\"
      {job_description}
      \"\"\"
      """

completion = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "developer", "content": prompt}],
        temperature=0.3,
        max_tokens=10
)

score = (completion.choices[0].message.content)

print("Green Score", score)
