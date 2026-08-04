# CyberNexa LLM Provider Cost Comparison

These values are taken from the project configuration in `config/llm_config.yaml`. They are configured estimates for governance and demonstration purposes, not independently verified live vendor pricing.

| Provider | Model | Input cost per 1M tokens | Output cost per 1M tokens | Example cost: 1,000 input + 500 output tokens |
|---|---|---:|---:|---:|
| Ollama | llama3.2 | $0.00 | $0.00 | $0.000000 |
| Groq | openai/gpt-oss-120b | $0.15 | $0.60 | $0.000450 |
| OpenAI | gpt-5-mini | $0.25 | $2.00 | $0.001250 |

## Notes

- Ollama has no external API usage charge in this configuration. Local hardware, electricity and maintenance costs are not included.
- Groq and OpenAI costs are estimated using the configured token rates.
- CyberNexa uses these values to estimate usage and enforce the daily budget cap.
