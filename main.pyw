import pyperclip
from pynput import keyboard
import pyautogui
import tkinter as tk
from tkinter import messagebox
import time
import threading
import requests
import queue


# --- AYARLAR ---
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_ADI = "gpt-oss:120b-cloud"  # Radyoloji Rapor Asistanı modeli (F8)
TEXT_MODEL_CANDIDATES = [
    MODEL_ADI,
    "gpt-oss:120b",
    "gpt-oss:latest",
]

KISAYOL_METIN = keyboard.Key.f8  # Metin seçimi için kısayol

SISTEM_PROMPT = """Sen deneyimli bir sağlık asistanısın. Kullanıcılar sana MR, BT (Bilgisayarlı Tomografi) veya diğer radyoloji raporlarını gönderiyor. Aşağıdaki kurallara KESINLIKLE uy:

KURALLAR:
1. Tıbbi terimleri mümkün olduğunca sadeleştir ve gerekiyorsa kısa parantez içi açıklama ekle.
2. Korkutucu veya kesin tanı koyan ifadeler KULLANMA. "Kesinlikle şu hastalık var" gibi cümleler kurma.
3. Her yanıtın sonuna şu uyarıyı ekle: "⚠️ Bu bir doktor tanısı değildir. Lütfen uzman hekiminize başvurunuz."
4. Metinde olmayan bilgileri UYDURMA. Belirsiz bir durum varsa "Bu bilgiye göre kesin bir şey söylenemez" de.
5. Açıklamalar kısa, net ve günlük dilde olsun.
6. Acil durumları fark edersen hastayı uyar.
"""

# Global değişkenler
root = None
gui_queue = queue.Queue()
kisayol_basildi = False


# --- MENÜ SEÇENEKLERİ VE PROMPT'LAR ---
ISLEMLER = {
    "📋 Raporun Basit Özeti": (
        "Aşağıdaki radyoloji raporunu oku ve hastanın anlayabileceği şekilde özetle.\n"
        "Çıktı formatı:\n"
        "[Başlık: Raporun Basit Özeti]\n"
        "- Bu rapora göre ...\n"
        "- Önemli bulunan durum: ...\n"
        "(Her madde kısa ve anlaşılır olsun. Tıbbi terimler varsa parantez içinde açıkla.)"
    ),
    "❓ Ne Anlama Geliyor?": (
        "Aşağıdaki radyoloji raporundaki bulguları analiz et ve hastanın anlayabileceği şekilde açıkla.\n"
        "Çıktı formatı:\n"
        "[Başlık: Ne Anlama Geliyor?]\n"
        "- Bu durum genellikle ...\n"
        "- Ciddi olup olmadığı için doktor değerlendirmesi gerekir\n"
        "(Kesin tanı koyma, sadece genel bilgi ver.)"
    ),
    "💊 Tedavi / Yapılması Gerekenler": (
        "Aşağıdaki radyoloji raporunu inceleyerek hastaya ne yapması gerektiğini anlat.\n"
        "Çıktı formatı:\n"
        "[Başlık: Tedavi / Yapılması Gerekenler]\n"
        "- Doktora başvurulması önerilir\n"
        "- Gerekirse ilaç veya fizik tedavi planlanabilir\n"
        "(Kesin tedavi önerme, sadece genel tavsiye ver.)"
    ),
    "🔬 Gerekirse Ek Tetkikler": (
        "Aşağıdaki radyoloji raporunu inceleyerek hangi ek tetkiklerin gerekebileceğini açıkla.\n"
        "Çıktı formatı:\n"
        "[Başlık: Gerekirse Ek Tetkikler]\n"
        "- Bu bulgular için ek olarak ... istenebilir\n"
        "- Doktorunuz gerekli görürse ...\n"
        "(Sadece rapordaki bulgulara dayanarak öner, hayal etme.)"
    ),
    "📅 Takip Süreci": (
        "Aşağıdaki radyoloji raporunu inceleyerek hastanın nasıl bir takip sürecinden geçmesi gerektiğini anlat.\n"
        "Çıktı formatı:\n"
        "[Başlık: Takip Süreci]\n"
        "- Ne zaman kontrol gerekir: ...\n"
        "- Dikkat edilmesi gereken belirtiler: ...\n"
        "- Acil başvuruyu gerektiren durumlar: ...\n"
        "(Kısa ve net ol.)"
    ),
}


def get_available_text_model():
    """Metin işlemede kullanılabilir modeli seçer."""
    preferred_models = []
    for model in TEXT_MODEL_CANDIDATES:
        if model and model not in preferred_models:
            preferred_models.append(model)

    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code != 200:
            return MODEL_ADI

        models = response.json().get("models", [])
        installed_lower = {m.get("name", "").lower(): m.get("name", "") for m in models}

        for candidate in preferred_models:
            candidate_lower = candidate.lower()
            if candidate_lower in installed_lower:
                return installed_lower[candidate_lower]

            candidate_base = candidate_lower.split(":")[0]
            for installed_name_lower, installed_name in installed_lower.items():
                if installed_name_lower.startswith(candidate_base + ":"):
                    return installed_name
    except Exception:
        pass

    return MODEL_ADI


def ollama_cevap_al(prompt, sistem_prompt=None):
    """Ollama API'den cevap al."""
    try:
        aktif_model = get_available_text_model()

        # Sistem promptunu dahil et
        full_prompt = ""
        if sistem_prompt:
            full_prompt = f"{sistem_prompt}\n\n---\n\n{prompt}"
        else:
            full_prompt = prompt

        payload = {
            "model": aktif_model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": 0.4,
                "top_p": 0.9,
                "num_ctx": 4096,
            },
        }

        response = requests.post(OLLAMA_URL, json=payload, timeout=120)

        if response.status_code == 200:
            result = response.json()
            return result.get("response", "").strip()

        err_msg = (
            f"Ollama API Hatası: {response.status_code}\n"
            f"Model: {aktif_model}\n"
            f"Cevap: {response.text}"
        )
        print(f"❌ {err_msg}")
        gui_queue.put((messagebox.showerror, ("API Hatası", err_msg)))
        return None

    except requests.exceptions.ConnectionError:
        err_msg = (
            "Ollama'ya bağlanılamadı.\n"
            "Programın çalıştığından emin olun!\n"
            "(http://localhost:11434)"
        )
        print(f"❌ {err_msg}")
        gui_queue.put((messagebox.showerror, ("Bağlantı Hatası", err_msg)))
        return None
    except Exception as e:
        err_msg = f"Beklenmeyen Hata: {e}"
        print(f"❌ {err_msg}")
        gui_queue.put((messagebox.showerror, ("Hata", err_msg)))
        return None


def secili_metni_kopyala(max_deneme=4):
    sentinel = f"__SAGLIK_ASISTANI__{time.time_ns()}__"
    try:
        pyperclip.copy(sentinel)
    except Exception:
        pass

    for _ in range(max_deneme):
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.2)
        metin = pyperclip.paste()
        if metin and metin.strip() and metin != sentinel:
            return metin
    return ""


def sonuc_penceresi_goster(baslik, icerik):
    """Sonuç penceresini göster."""
    pencere = tk.Toplevel(root)
    pencere.title(f"🏥 Radyoloji Rapor Asistanı — {baslik}")
    pencere.geometry("860x600")
    pencere.minsize(600, 400)
    pencere.attributes("-topmost", True)
    pencere.configure(bg="#0d1117")

    # Başlık çubuğu
    baslik_frame = tk.Frame(pencere, bg="#161b22", pady=12)
    baslik_frame.pack(fill="x")

    tk.Label(
        baslik_frame,
        text="🏥 Radyoloji Rapor Asistanı",
        font=("Segoe UI", 12, "bold"),
        bg="#161b22",
        fg="#58a6ff",
    ).pack(side="left", padx=16)

    tk.Label(
        baslik_frame,
        text=baslik,
        font=("Segoe UI", 11),
        bg="#161b22",
        fg="#8b949e",
    ).pack(side="left", padx=4)

    # Uyarı bandı
    uyari_frame = tk.Frame(pencere, bg="#3d1f00", pady=6)
    uyari_frame.pack(fill="x")
    tk.Label(
        uyari_frame,
        text="⚠️  Bu uygulama bilgilendirme amaçlıdır. Doktor tanısı değildir. Hekiminize başvurunuz.",
        font=("Segoe UI", 9),
        bg="#3d1f00",
        fg="#ffa657",
    ).pack(padx=14)

    # İçerik alanı
    frame = tk.Frame(pencere, bg="#0d1117")
    frame.pack(fill="both", expand=True, padx=14, pady=10)

    text_alani = tk.Text(
        frame,
        wrap="word",
        bg="#161b22",
        fg="#e6edf3",
        insertbackground="#e6edf3",
        font=("Segoe UI", 10),
        padx=14,
        pady=14,
        relief="flat",
        borderwidth=0,
        spacing1=2,
        spacing3=4,
    )
    kaydirma = tk.Scrollbar(frame, command=text_alani.yview, bg="#21262d", troughcolor="#161b22")
    text_alani.configure(yscrollcommand=kaydirma.set)

    text_alani.pack(side="left", fill="both", expand=True)
    kaydirma.pack(side="right", fill="y")

    text_alani.insert("1.0", icerik)
    text_alani.config(state="disabled")

    # Alt butonlar
    alt_frame = tk.Frame(pencere, bg="#161b22", pady=10)
    alt_frame.pack(fill="x", padx=14)

    def panoya_kopyala():
        pyperclip.copy(icerik)
        btn_kopyala.config(text="✅ Kopyalandı!")
        pencere.after(1500, lambda: btn_kopyala.config(text="📋 Panoya Kopyala"))

    btn_kopyala = tk.Button(
        alt_frame,
        text="📋 Panoya Kopyala",
        command=panoya_kopyala,
        bg="#21262d",
        fg="#e6edf3",
        activebackground="#30363d",
        activeforeground="#e6edf3",
        relief="flat",
        padx=14,
        pady=7,
        font=("Segoe UI", 9),
        cursor="hand2",
    )
    btn_kopyala.pack(side="left", padx=(0, 8))

    tk.Button(
        alt_frame,
        text="❌ Kapat",
        command=pencere.destroy,
        bg="#21262d",
        fg="#e6edf3",
        activebackground="#30363d",
        activeforeground="#e6edf3",
        relief="flat",
        padx=14,
        pady=7,
        font=("Segoe UI", 9),
        cursor="hand2",
    ).pack(side="right")

    pencere.focus_force()
    pencere.lift()


def yukleniyor_penceresi_goster(baslik):
    """Yükleniyor göstergesi."""
    pencere = tk.Toplevel(root)
    pencere.title("Radyoloji Rapor Asistanı")
    pencere.geometry("380x120")
    pencere.resizable(False, False)
    pencere.attributes("-topmost", True)
    pencere.configure(bg="#0d1117")

    tk.Label(
        pencere,
        text="🏥 Radyoloji Rapor Asistanı",
        font=("Segoe UI", 11, "bold"),
        bg="#0d1117",
        fg="#58a6ff",
    ).pack(pady=(16, 4))

    tk.Label(
        pencere,
        text=f"⏳ İşleniyor: {baslik}...",
        font=("Segoe UI", 10),
        bg="#0d1117",
        fg="#8b949e",
    ).pack()

    # İlerleme çubuğu animasyonu
    progress_label = tk.Label(
        pencere,
        text="",
        font=("Segoe UI", 9),
        bg="#0d1117",
        fg="#238636",
    )
    progress_label.pack(pady=6)

    dots = ["", ".", "..", "...", "...."]
    dot_idx = [0]

    def animate():
        if pencere.winfo_exists():
            progress_label.config(text=f"Analiz ediliyor{dots[dot_idx[0] % len(dots)]}")
            dot_idx[0] += 1
            pencere.after(400, animate)

    animate()
    return pencere


def islemi_yap(komut_adi, secili_metin):
    """Seçilen işlemi Ollama ile yap ve sonucu pencerede göster."""
    prompt_emri = ISLEMLER[komut_adi]
    full_prompt = f"{prompt_emri}\n\n---\nRADYOLOJİ RAPORU:\n{secili_metin}\n---"

    print(f"🏥 İşlem: {komut_adi}")
    print("⏳ Ollama ile analiz ediliyor...")

    # Yükleniyor penceresi aç
    yukleniyor_ref = [None]

    def ac_yukleniyor():
        yukleniyor_ref[0] = yukleniyor_penceresi_goster(komut_adi)

    gui_queue.put((ac_yukleniyor, ()))
    time.sleep(0.3)

    sonuc = ollama_cevap_al(full_prompt, sistem_prompt=SISTEM_PROMPT)

    # Yükleniyor penceresini kapat
    def kapat_yukleniyor():
        if yukleniyor_ref[0] and yukleniyor_ref[0].winfo_exists():
            yukleniyor_ref[0].destroy()

    gui_queue.put((kapat_yukleniyor, ()))

    if not sonuc:
        print("❌ Sonuç alınamadı.")
        return

    # Uyarı zaten sistemde var, ama modelin eklemediği durumlar için kontrol
    if "doktor tanısı değildir" not in sonuc.lower():
        sonuc += "\n\n⚠️ Bu bir doktor tanısı değildir. Lütfen uzman hekiminize başvurunuz."

    gui_queue.put((sonuc_penceresi_goster, (komut_adi, sonuc)))
    print("✅ Analiz tamamlandı!")


def process_queue():
    """Kuyruktaki GUI işlemlerini ana thread'de çalıştırır."""
    try:
        while True:
            try:
                task = gui_queue.get_nowait()
            except queue.Empty:
                break
            func, args = task
            if callable(func):
                func(*args)
            else:
                # (func, args) değil sadece (func, ()) formatı için
                func()
    finally:
        if root:
            root.after(100, process_queue)


def menu_goster():
    """Metni kopyalar ve sağlık menüsünü gösterir (ana thread)."""
    secili_metin = secili_metni_kopyala()
    if not secili_metin.strip():
        gui_queue.put(
            (
                messagebox.showwarning,
                (
                    "Seçim Bulunamadı",
                    "Lütfen önce radyoloji raporu metnini seçin, sonra F8 ile menüyü açın.",
                ),
            )
        )
        return

    menu = tk.Menu(
        root,
        tearoff=0,
        bg="#161b22",
        fg="#e6edf3",
        activebackground="#388bfd",
        activeforeground="white",
        font=("Segoe UI", 10),
        borderwidth=0,
        relief="flat",
    )

    # Başlık etiketi (tıklanamaz)
    menu.add_command(
        label="🏥 Radyoloji Rapor Asistanı — Radyoloji Raporu",
        state="disabled",
        font=("Segoe UI", 9, "bold"),
    )
    menu.add_separator()

    def komut_olustur(k_adi, s_metin):
        def komut_calistir():
            threading.Thread(
                target=islemi_yap, args=(k_adi, s_metin), daemon=True
            ).start()

        return komut_calistir

    for baslik in ISLEMLER.keys():
        menu.add_command(label=baslik, command=komut_olustur(baslik, secili_metin))

    menu.add_separator()
    menu.add_command(label="❌ İptal", command=lambda: None)

    try:
        x, y = pyautogui.position()
        menu.tk_popup(x, y)
    finally:
        menu.grab_release()


def on_press(key):
    global kisayol_basildi
    try:
        if key == KISAYOL_METIN and not kisayol_basildi:
            kisayol_basildi = True
            gui_queue.put((menu_goster, ()))
    except AttributeError:
        pass


def on_release(key):
    global kisayol_basildi
    try:
        if key == KISAYOL_METIN:
            kisayol_basildi = False
    except AttributeError:
        pass


if __name__ == "__main__":
    print("=" * 60)
    print("🏥 Radyoloji Rapor Asistanı — Radyoloji Raporu Analizi")
    print("=" * 60)
    aktif_model = get_available_text_model()
    print(f"📦 Model (F8): {aktif_model}")
    print()
    print("🔧 Kullanım:")
    print("   1. Radyoloji raporu metnini seçin")
    print("   2. F8 tuşuna basın")
    print("   3. Açılan menüden işlem seçin")
    print()
    print("📋 Menü Seçenekleri:")
    for k in ISLEMLER.keys():
        print(f"   {k}")
    print()
    print("⚠️  Bu program bilgilendirme amaçlıdır, doktor tanısı değildir!")
    print("⚠️  Programı kapatmak için bu pencereyi kapatın veya Ctrl+C yapın.")
    print("=" * 60)

    try:
        test_response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if test_response.status_code == 200:
            print("✅ Ollama bağlantısı başarılı!")
            modeller = test_response.json().get("models", [])
            if modeller:
                print("📦 Yüklü modeller:")
                for m in modeller:
                    print(f"   - {m.get('name', '?')}")
            else:
                print("⚠️  Hiç model yüklü değil! 'ollama pull gpt-oss:120b-cloud' çalıştırın.")
        else:
            print("⚠️  Ollama'ya bağlanılamadı, servisi kontrol edin!")
    except Exception:
        print("⚠️  Ollama çalışmıyor! Terminalde 'ollama serve' ile başlatın.")

    print()

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    root = tk.Tk()
    root.withdraw()
    root.after(100, process_queue)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("Kapatılıyor...")
