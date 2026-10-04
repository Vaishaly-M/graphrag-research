from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from google import genai


PREFERRED_MODELS = (
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash-preview",
    "gemini-3.5-flash",
)


def main() -> None:
    load_dotenv()

    api_key = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
    )

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY or GOOGLE_API_KEY is missing from .env"
        )

    client = genai.Client(api_key=api_key)

    try:
        print("Models available to this API key")
        print("-" * 70)

        available_models: list[str] = []

        for model in client.models.list():
            model_name = getattr(model, "name", "") or ""

            if not model_name:
                continue

            clean_name = model_name.removeprefix("models/")
            available_models.append(clean_name)

            supported_actions = (
                getattr(model, "supported_actions", None)
                or getattr(model, "supported_generation_methods", None)
                or []
            )

            print(
                f"{clean_name:45s} "
                f"{', '.join(map(str, supported_actions))}"
            )

        if not available_models:
            raise RuntimeError(
                "The API returned no available models."
            )

        selected_model = next(
            (
                model
                for model in PREFERRED_MODELS
                if model in available_models
            ),
            None,
        )

        if selected_model is None:
            selected_model = next(
                (
                    model
                    for model in available_models
                    if "flash" in model.lower()
                    and "embedding" not in model.lower()
                    and "image" not in model.lower()
                    and "tts" not in model.lower()
                    and "audio" not in model.lower()
                ),
                None,
            )

        if selected_model is None:
            raise RuntimeError(
                "No text-generation Flash model was found."
            )

        print("\nSelected model")
        print("-" * 70)
        print(selected_model)

        response = client.models.generate_content(
            model=selected_model,
            contents="Reply with exactly: API_OK",
        )

        response_text = (response.text or "").strip()

        print("\nResponse")
        print("-" * 70)
        print(response_text)

        if "API_OK" not in response_text:
            raise RuntimeError(
                "The model responded, but did not return API_OK."
            )

        print("\nGemini API test passed.")
        print(
            f"Add this to .env:\n"
            f"GEMINI_MODEL={selected_model}"
        )

    except Exception as exc:
        print("\nGemini API test failed.")
        print(f"Error type: {type(exc).__name__}")
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()