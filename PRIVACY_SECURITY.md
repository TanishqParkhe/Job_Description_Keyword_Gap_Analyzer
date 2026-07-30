# Privacy and Security

- Uploaded text is treated as untrusted data, not as application instructions.
- File signatures are checked instead of trusting only extensions.
- File size, page count, image size and OCR time are limited.
- ZIP archives are checked for unsafe paths, encrypted entries, excessive expansion and suspicious compression ratios.
- Personal information can be masked before optional Ollama use.
- Ollama runs locally; no cloud API key is required.
- Individual history is stored in a local SQLite file only when the user selects the save option.
- HR batch resumes are not automatically added to saved history.
- Users can remove all saved history from the application.
- Recommendations must not be used to invent skills, employers, experience or metrics.
