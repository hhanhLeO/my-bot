import os
import argparse

from uploader import get_client, load_store_config

GENERATION_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6")

SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""


def ask(question: str, store_id: str | None = None) -> None:
    """Send a question to OptiBot (Responses API + file_search) and print the answer with citations."""
    client = get_client()

    if not store_id:
        store_id = load_store_config().get("vector_store_id")
    if not store_id:
        raise ValueError("No vector store found. Run 'uploader.py' first.")

    response = client.responses.create(
        model=GENERATION_MODEL,
        instructions=SYSTEM_PROMPT,
        input=question,
        tools=[{"type": "file_search", "vector_store_ids": [store_id]}],
    )

    print(response.output_text)

    # Collect file citations from the message annotations.
    sources = []
    for item in response.output:
        if getattr(item, "type", None) == "message":
            for block in item.content:
                for ann in getattr(block, "annotations", None) or []:
                    if getattr(ann, "type", None) == "file_citation":
                        name = getattr(ann, "filename", None)
                        if name and name not in sources:
                            sources.append(name)

    if sources:
        print("\nSources:")
        for name in sources:
            print(f"  - {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask OptiBot a question.")
    parser.add_argument("question", help="Question to ask")
    parser.add_argument("--store", default=os.getenv("OPENAI_VECTOR_STORE_ID"), metavar="STORE_ID")
    args = parser.parse_args()
    ask(args.question, store_id=args.store)


if __name__ == "__main__":
    main()
