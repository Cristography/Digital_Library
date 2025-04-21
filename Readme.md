# Digital Library — Documentation  
**Version:** 1.0  

---

📷 Screenshots (optional)  
Show what the app looks like.

---

## 🧠 Summary  
Digital Library is a desktop application for managing your personal digital content.  
It supports video/audio playback and PDF reading, while keeping track of your progress, last opened times, and allowing you to take notes directly within the app.

---

## ⚙️ How It Works  
- The GUI is built using `customtkinter`  
- Video and audio are played with `python-vlc`  
- PDFs are rendered using `PyMuPDF`  
- All user interactions (last page, playback progress) are saved in local JSON  
- App settings are stored in a config `.ini` file  
- Includes a note editor with font customization

---

## 💾 Requirements  

- **Python Version:** 3.x  
- **Main Libraries Used:**  
  - `customtkinter` for GUI  
  - `python-vlc` for media playback  
  - `fitz` (PyMuPDF) for PDF rendering  
  - `Pillow` for image handling  
  - `configparser`, `json`, `logging` for backend logic  

---

## 🖥️ User Instructions  

1. Clone the repository or download the `.zip` file.  
2. Install the requirements:  
   ```bash
   pip install -r requirements.txt
3. Run the app:
    ```bash
    python main.py
4. Add media files into the library folder.
5. Use the interface to open, view, or take notes.

---
Known Issues:
* PDF zooming may become slow on large files.
* Playback may not embed properly on macOS.