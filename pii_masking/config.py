"""Masking labels and NER exclusions ported from kouki6951/pii-masking-chat."""

import os
from pathlib import Path

from dotenv import dotenv_values

MAX_TEXT_LENGTH = 1024 ** 2
DOTENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_settings() -> dict[str, str | None]:
    """Read repository-local .env; explicit environment variables take priority."""
    return {**dotenv_values(DOTENV_PATH, interpolate=False), **os.environ}


def parse_filters(value: str | None) -> list[str] | None:
    """None enables all filters; empty or unknown selections fail closed."""
    if value is None:
        return None
    filters = list(dict.fromkeys(part.strip() for part in value.split(",")))
    if not filters or any(entity not in ENTITY_LABELS_JA for entity in filters):
        raise ValueError("PII_FILTERS must contain supported entity types")
    return filters


ENTITY_LABELS_JA = {
    "PERSON": "氏名",
    "LOCATION": "地名",
    "ORGANIZATION": "組織名",
    "NRP": "国籍・宗教・政治的集団",
    "DATE_TIME": "日時",
    "EMAIL_ADDRESS": "メールアドレス",
    "CREDIT_CARD": "クレジットカード番号",
    "IP_ADDRESS": "IPアドレス",
    "URL": "URL",
    "PHONE_NUMBER": "電話番号",
    "JP_MY_NUMBER": "マイナンバー",
    "JP_POSTAL_CODE": "郵便番号",
    "JP_ADDRESS": "住所",
    "JP_PASSPORT": "パスポート番号",
    "JP_DRIVERS_LICENSE": "運転免許証番号",
    "JP_BANK_ACCOUNT": "銀行口座番号",
}

NER_DENYLIST = frozenset({
    "お客", "お客様", "宛先", "担当", "担当者", "御中", "各位", "弊社",
    "当社", "貴社", "本社", "先方", "本人", "出席者", "参加者", "申込者",
    "応募者", "差出人", "支払先", "振込先", "納品先", "件名", "本文",
    "署名", "添付", "概要", "拝啓", "敬具", "議事録", "議題", "会議",
    "会議室", "オフィス",
})

DENYLIST_ENTITIES = frozenset({"PERSON", "ORGANIZATION", "LOCATION"})
