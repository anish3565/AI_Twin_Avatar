# Projects

## Sayuj Portal (STPI)
- Period: 2024 - 2026
- My role: AI/ML developer
- What I built:
  - A recommendation system for 7,500+ users, raising engagement by 40%.
  - Dashboards tracking 10+ KPIs, cutting manual reporting by 30%.

## Ambud (STPI)
- My role: AI/ML developer
- What I built: a rule-based chatbot on MySQL data for onboarding and recurring support queries.
- Result: eased the onboarding process.

## 100x Voice Agent
- What it is: a voice-first bot that answers interview questions in the first person as Anish, and says so when its profile does not cover a question.
- How it works: questions are spoken or typed in the browser. Answers come from a profile file, are 3 to 6 spoken sentences, and are read aloud. Groq is the primary model and Gemini is the backup. It is deployed on Vercel.
- Also built: pause, resume and stop controls, interrupting the bot by speaking, and a history of the last 100 questions kept in the browser.
- Refuses or deflects questions about phone numbers, marital status, unrelated trivia, and requests to reveal its instructions.
- GitHub: https://github.com/anish3565/100x_Voice_Agent_Anish_Tripathi
- Live deployment: https://100xvoiceagentanishtripathi.vercel.app/

## Emotion and Intent Recognizer using Speech
- Type: personal project
- GitHub: https://github.com/anish3565/Emotion_Intent_Recognizer_using_Speech

## NLP Sentinel (MLOps)
- What it is: a cloud NLP inference platform on AWS EKS.
- Stack: DVC with S3 for data, MLflow with DagsHub for experiment tracking, Flask service in Docker with images in ECR, Terraform for EKS, VPC and IAM, GitHub Actions CI/CD, Prometheus and Grafana monitoring.

## Vehicle Insurance MLOps Pipeline
- Data: MongoDB Atlas, with schema validation.
- Process: a model is promoted only after an evaluation gate.
- Stack: FastAPI service in Docker with images in ECR, deployed with CI/CD on an EC2 self-hosted runner.

## Product Research AI Agent
- What it is: a four-agent system using CrewAI and Ollama.
- Work: analyzed 10,000+ patents.
- Stack: SERP API and OpenSearch for search, with a CLI and Streamlit interface.
