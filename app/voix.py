"""Transcription d'une note vocale (micro de l'interface, note vocale reçue sur WhatsApp).

Ordre : Groq (Whisper), puis Gemini. La transcription devient le texte de la commande : elle passe
ensuite par la même lecture, les mêmes citations vérifiées et la même validation humaine.
"""
from __future__ import annotations

import os

import httpx

from .extraction import ErreurExtraction

EXTENSIONS_AUDIO = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a",
                    "audio/x-m4a": "m4a", "audio/m4a": "m4a", "audio/aac": "m4a", "audio/wav": "wav",
                    "audio/x-wav": "wav"}
TAILLE_MAX = 10 * 1024 * 1024
GROQ_URL_VOIX = "https://api.groq.com/openai/v1/audio/transcriptions"


def _verifier(octets: bytes, mime: str | None) -> str:
    mime = (mime or "").split(";")[0].strip().lower()
    if mime not in EXTENSIONS_AUDIO:
        raise ErreurExtraction("Format audio non pris en charge.")
    if not octets:
        raise ErreurExtraction("Enregistrement vide.")
    if len(octets) > TAILLE_MAX:
        raise ErreurExtraction("Note vocale trop longue (10 Mo au plus).")
    return mime


def _groq(octets: bytes, mime: str) -> str:
    r = httpx.post(os.environ.get("GROQ_URL_VOIX") or GROQ_URL_VOIX,
                   headers={"Authorization": "Bearer " + os.environ["GROQ_API_KEY"]},
                   data={"model": os.environ.get("GROQ_MODELE_VOIX", "whisper-large-v3-turbo"), "language": "fr",
                         "temperature": "0", "response_format": "json"},
                   files={"file": ("note." + EXTENSIONS_AUDIO[mime], octets, mime)}, timeout=60)
    if r.status_code == 429:
        raise ErreurExtraction("quota gratuit atteint")
    if r.status_code != 200:
        raise ErreurExtraction(f"refus ({r.status_code})")
    return (r.json().get("text") or "").strip()


def _gemini(octets: bytes, mime: str) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                          http_options=types.HttpOptions(api_version="v1beta", timeout=60000))
    r = client.models.generate_content(
        model=os.environ.get("GEMINI_MODELE_VOIX", "gemini-3.5-flash-lite"),
        contents=[types.Part.from_bytes(data=octets, mime_type=mime),
                  "Transcris mot pour mot cette note vocale (français, souvent familier). "
                  "Réponds uniquement par la transcription, sans rien ajouter."],
        config=types.GenerateContentConfig(temperature=0))
    return (r.text or "").strip()


def transcrire(octets: bytes, mime: str | None) -> tuple[str, str]:
    """Renvoie (texte, moteur). Lève ErreurExtraction si aucune IA ne répond."""
    mime = _verifier(octets, mime)
    echecs = []
    for nom, cle, fonction in (("Groq Whisper", "GROQ_API_KEY", _groq), ("Gemini", "GEMINI_API_KEY", _gemini)):
        if not os.environ.get(cle):
            continue
        try:
            texte = fonction(octets, mime)
        except ErreurExtraction as e:
            echecs.append(f"{nom} : {e}")
            continue
        except Exception as e:  # réseau, délai, réponse inattendue
            echecs.append(f"{nom} : {type(e).__name__}")
            continue
        if texte:
            return texte, nom
        echecs.append(f"{nom} : rien entendu")
    if not echecs:
        raise ErreurExtraction("Aucune clé d'IA configurée pour transcrire la voix.")
    raise ErreurExtraction("Transcription impossible. " + " ; ".join(echecs))
