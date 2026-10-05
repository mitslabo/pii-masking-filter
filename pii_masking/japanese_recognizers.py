"""Japanese Presidio patterns ported from kouki6951/pii-masking-chat.

Lookarounds allow email/card detection next to Japanese characters.
Names are additionally recognized by spaCy NER and honorifics.
"""

from presidio_analyzer import Pattern, PatternRecognizer

_HYPHEN = r"[-‐‑‒–—―ーｰ－]"
_DIGIT = r"[0-9０-９]"
_SEP = r"[ 　‐‑‒–—―ーｰ－-]?"
_PREFECTURES = (
    "北海道|青森県|岩手県|宮城県|秋田県|山形県|福島県|茨城県|栃木県|群馬県|"
    "埼玉県|千葉県|東京都|神奈川県|新潟県|富山県|石川県|福井県|山梨県|長野県|"
    "岐阜県|静岡県|愛知県|三重県|滋賀県|京都府|大阪府|兵庫県|奈良県|和歌山県|"
    "鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|愛媛県|高知県|福岡県|"
    "佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄県"
)


def _email_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="EMAIL_ADDRESS",
        name="JpEmailRecognizer",
        supported_language="ja",
        patterns=[Pattern(
            name="jp_email",
            regex=r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
            score=0.9,
        )],
        context=["メール", "アドレス", "email", "e-mail", "連絡先"],
    )


def _credit_card_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="CREDIT_CARD",
        name="JpCreditCardRecognizer",
        supported_language="ja",
        patterns=[Pattern(
            name="jp_credit_card",
            regex=(
                r"(?<![0-9０-９])"
                rf"{_DIGIT}{{4}}{_SEP}{_DIGIT}{{4}}{_SEP}{_DIGIT}{{4}}{_SEP}{_DIGIT}{{4}}"
                r"(?![0-9０-９])"
            ),
            score=0.7,
        )],
        context=["カード", "クレジット", "クレカ", "card"],
    )


def _phone_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="PHONE_NUMBER",
        name="JpPhoneRecognizer",
        supported_language="ja",
        patterns=[
            Pattern(
                name="jp_mobile",
                regex=rf"0[789]0{_HYPHEN}?{_DIGIT}{{4}}{_HYPHEN}?{_DIGIT}{{4}}",
                score=0.7,
            ),
            Pattern(
                name="jp_freedial",
                regex=rf"0120{_HYPHEN}?{_DIGIT}{{2,3}}{_HYPHEN}?{_DIGIT}{{3,4}}",
                score=0.7,
            ),
            Pattern(
                name="jp_landline",
                regex=rf"0{_DIGIT}{{1,3}}{_HYPHEN}{_DIGIT}{{1,4}}{_HYPHEN}{_DIGIT}{{4}}",
                score=0.65,
            ),
            Pattern(
                name="jp_mobile_plain",
                regex=r"(?<![0-9０-９])0[789]0[0-9０-９]{8}(?![0-9０-９])",
                score=0.4,
            ),
        ],
        context=["電話", "TEL", "tel", "携帯", "連絡先", "番号"],
    )


def _my_number_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="JP_MY_NUMBER",
        name="JpMyNumberRecognizer",
        supported_language="ja",
        patterns=[
            Pattern(
                name="jp_mynumber_grouped",
                regex=rf"(?<![0-9０-９]){_DIGIT}{{4}}{_SEP}{_DIGIT}{{4}}"
                rf"{_SEP}{_DIGIT}{{4}}(?![0-9０-９])",
                score=0.6,
            ),
            Pattern(
                name="jp_mynumber_plain",
                regex=r"(?<![0-9０-９])[0-9０-９]{12}(?![0-9０-９])",
                score=0.3,
            ),
        ],
        context=["マイナンバー", "個人番号", "マイ ナンバー"],
    )


def _postal_code_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="JP_POSTAL_CODE",
        name="JpPostalCodeRecognizer",
        supported_language="ja",
        patterns=[
            Pattern(
                name="jp_postal_mark",
                regex=rf"〒\s?{_DIGIT}{{3}}{_HYPHEN}?{_DIGIT}{{4}}",
                score=0.65,
            ),
            Pattern(
                name="jp_postal_plain",
                regex=rf"(?<![0-9０-９]){_DIGIT}{{3}}{_HYPHEN}{_DIGIT}{{4}}(?![0-9０-９])",
                score=0.6,
            ),
        ],
        context=["郵便番号", "郵便", "番号", "〒", "住所"],
    )


def _address_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="JP_ADDRESS",
        name="JpAddressRecognizer",
        supported_language="ja",
        patterns=[Pattern(
            name="jp_address",
            regex=(
                rf"(?:{_PREFECTURES})"
                rf"[^\s、。,]{{1,20}}?"
                rf"(?:{_DIGIT}+|[一二三四五六七八九十]+)"
                rf"(?:{_HYPHEN}{_DIGIT}+)*"
                r"(?:丁目|番地|番|号|条)?"
            ),
            score=0.5,
        )],
        context=["住所", "在住", "居住", "所在地", "番地"],
    )


def _bank_account_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="JP_BANK_ACCOUNT",
        name="JpBankAccountRecognizer",
        supported_language="ja",
        patterns=[Pattern(
            name="jp_bank_account",
            regex=r"(?<![0-9０-９])[0-9０-９]{7,8}(?![0-9０-９])",
            score=0.3,
        )],
        context=["口座", "振込", "振込先", "普通", "当座", "預金", "銀行", "支店"],
    )


def _passport_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="JP_PASSPORT",
        name="JpPassportRecognizer",
        supported_language="ja",
        patterns=[Pattern(
            name="jp_passport",
            regex=r"(?<![A-Za-z0-9])[A-Z]{2}[0-9]{7}(?![A-Za-z0-9])",
            score=0.5,
        )],
        context=["パスポート", "旅券"],
    )


def _drivers_license_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="JP_DRIVERS_LICENSE",
        name="JpDriversLicenseRecognizer",
        supported_language="ja",
        patterns=[Pattern(
            name="jp_drivers_license",
            regex=r"(?<![0-9０-９])[0-9０-９]{12}(?![0-9０-９])",
            score=0.3,
        )],
        context=["免許", "運転免許", "免許証"],
    )


def _person_honorific_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="PERSON",
        name="JpPersonHonorificRecognizer",
        supported_language="ja",
        patterns=[Pattern(
            name="jp_person_honorific",
            regex=r"[一-龥々ぁ-んァ-ヶ]{2,10}"
            r"(?=(?:さん|様|氏|くん|君|ちゃん|先生|部長|課長|社長|専務|常務))",
            score=0.45,
        )],
    )


def get_japanese_recognizers() -> list[PatternRecognizer]:
    return [
        _email_recognizer(),
        _credit_card_recognizer(),
        _phone_recognizer(),
        _my_number_recognizer(),
        _postal_code_recognizer(),
        _address_recognizer(),
        _bank_account_recognizer(),
        _passport_recognizer(),
        _drivers_license_recognizer(),
        _person_honorific_recognizer(),
    ]
