# Full objective (from the lead, 2026-11-13)

## Objective
Build a working prototype that translates a limited vocabulary of American Sign Language (ASL) into English text and spoken audio using Meta smart glasses.

The user starts and stops video capture using a Meta Neural Band gesture. The captured video is processed, translated, and returned as English text and speech.

This is a prototype, NOT a general-purpose ASL translator.

## Tech stack
1. Frontend – Meta smart glasses
   - Meta Wearables Web App
   - HTML, CSS, JavaScript
   - Recording control via Neural Band gesture, if supported by the device SDK
   - Display translated English text
   - Play returned audio
   - Minimal, readable UI
   - IMPORTANT: Verify actual camera access for the selected Meta device and SDK. Do not assume a Web App can directly access the glasses camera. If necessary, use the Meta Device Access Toolkit through a supported mobile integration.
2. Backend
   - Python 3.11+
   - FastAPI
   - REST API for video upload and translation requests
   - OpenCV for video decoding and frame extraction
3. ASL recognition
   - MediaPipe Holistic for hand, face, and body landmarks
   - PyTorch for temporal sign classification
   - LSTM classifier as the initial baseline
   - Limited vocabulary of 10–20 ASL signs or phrases
   - Confidence scores for predictions
   - Reject low-confidence predictions rather than inventing translations
   - If a suitable pretrained ASL recognition model or dataset is available, evaluate it before training a custom model. Avoid training a large model from scratch.
4. Translation
   - Google Gemini API (Flash model)
   - Convert recognized sign labels/glosses into natural English
   - Provide context only from recognized signs
   - Never ask Gemini to guess signs that the recognition model did not identify
5. Text-to-speech
   - Gemini TTS API
   - Generate spoken English output
   - Return audio to the frontend
   - Browser audio playback
6. Hosting
   - Run FastAPI locally during development
   - Use Google Cloud Run only if remote hosting is needed
   - Avoid databases, authentication, and unnecessary infrastructure

## Processing pipeline
Meta Glasses Camera → Video Capture → FastAPI Backend → OpenCV Frame Extraction → MediaPipe Holistic → PyTorch LSTM Sign Classifier → Recognized ASL Glosses → Gemini English Translation → Gemini TTS → English Text + Audio → Meta Glasses Web App

## MVP user flow
1. User initiates recording using a supported Meta gesture.
2. User signs a predefined ASL phrase.
3. User stops recording.
4. Video is sent to the backend.
5. ASL recognition model identifies the signs.
6. Gemini converts recognized signs into natural English.
7. Gemini TTS generates spoken English.
8. Glasses display the translation and play audio.

## Engineering constraints
- Prioritize a working end-to-end demo over architectural sophistication.
- Avoid training large neural networks from scratch.
- Avoid MCP, databases, authentication, and streaming unless absolutely necessary.
- Do not claim full ASL translation.
- Preserve temporal information: ASL is not just static hand gestures.
- Include facial expressions and body landmarks where possible.
- Clearly indicate uncertain predictions.
- Keep video processing modular so the recognition model can be replaced later.

## Definition of done
A user can sign one of several supported ASL phrases in front of the Meta glasses, stop recording, and receive:
- An English text translation.
- Spoken English audio.

The complete flow must work reliably during a live demonstration.
