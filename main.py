import logging
import os
from typing import Any

import requests
from dotenv import load_dotenv
from supabase import Client, create_client


MESSAGE_TEMPLATE = "Olá, {name} tudo bem com você?"
DEFAULT_LIMIT = 3


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Variavel de ambiente obrigatoria ausente: {name}")
    return value


def get_limit() -> int:
    raw_limit = os.getenv("CONTACT_LIMIT", str(DEFAULT_LIMIT))

    try:
        limit = int(raw_limit)
    except ValueError as exc:
        raise RuntimeError("CONTACT_LIMIT deve ser um numero inteiro.") from exc

    if limit < 1:
        raise RuntimeError("CONTACT_LIMIT deve ser maior ou igual a 1.")

    return min(limit, DEFAULT_LIMIT)


def create_supabase_client() -> Client:
    return create_client(
        require_env("SUPABASE_URL"),
        require_env("SUPABASE_KEY"),
    )


def fetch_contacts(client: Client, limit: int) -> list[dict[str, Any]]:
    table_name = os.getenv("SUPABASE_TABLE", "contacts")
    name_column = os.getenv("CONTACT_NAME_COLUMN", "name")
    phone_column = os.getenv("CONTACT_PHONE_COLUMN", "phone")

    response = (
        client.table(table_name)
        .select(f"{name_column},{phone_column}")
        .limit(limit)
        .execute()
    )

    contacts = response.data or []
    valid_contacts = []

    for contact in contacts:
        name = str(contact.get(name_column, "")).strip()
        phone = str(contact.get(phone_column, "")).strip()

        if not name or not phone:
            logging.warning("Contato ignorado por nome ou telefone vazio: %s", contact)
            continue

        valid_contacts.append({"name": name, "phone": phone})

    return valid_contacts


def send_whatsapp_message(phone: str, message: str) -> None:
    instance_id = require_env("ZAPI_INSTANCE_ID")
    token = require_env("ZAPI_TOKEN")
    client_token = os.getenv("ZAPI_CLIENT_TOKEN")

    url = f"https://api.z-api.io/instances/{instance_id}/token/{token}/send-text"
    headers = {"Content-Type": "application/json"}

    if client_token:
        headers["Client-Token"] = client_token

    response = requests.post(
        url,
        json={"phone": phone, "message": message},
        headers=headers,
        timeout=20,
    )

    response.raise_for_status()


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    limit = get_limit()
    client = create_supabase_client()
    contacts = fetch_contacts(client, limit)

    if not contacts:
        logging.info("Nenhum contato valido encontrado para envio.")
        return

    for contact in contacts:
        message = MESSAGE_TEMPLATE.format(name=contact["name"])

        try:
            send_whatsapp_message(contact["phone"], message)
            logging.info("Mensagem enviada para %s (%s)", contact["name"], contact["phone"])
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else ""
            logging.error(
                "Erro HTTP ao enviar para %s (%s): %s %s",
                contact["name"],
                contact["phone"],
                exc,
                body,
            )
        except requests.RequestException as exc:
            logging.error(
                "Erro de conexao ao enviar para %s (%s): %s",
                contact["name"],
                contact["phone"],
                exc,
            )


if __name__ == "__main__":
    main()
