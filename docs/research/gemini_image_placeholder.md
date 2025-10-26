# Gemini image placeholder notes

## Why Gemini responses show `<image>`
- The Gemini API returns multimodal responses as a list of parts. Each part may include `text` or binary `inline_data` for images. 【9aefb7†L48-L88】
- When a client prints the response object directly, any `inline_data` part renders as a placeholder such as `<image>` because the raw binary payload is not automatically decoded into a file. Decoding the `inline_data` (for example, by reading the bytes into Pillow as shown in the docs) is required to materialize an actual image. 【9aefb7†L48-L88】

## Community reports
- Google AI forum topics like “Gemini Image - Repeated Finish Reason: IMAGE_OTHER” indicate other developers encounter Gemini image output issues that require follow-up. 【136614†L29-L60】

## Web search signal
- A Brave Search query for `Gemini "<image>"` returned “Too few matches were found,” so documentation on the placeholder behavior is sparse; most official guidance focuses on decoding `inline_data`. 【09f49d†L1-L74】
