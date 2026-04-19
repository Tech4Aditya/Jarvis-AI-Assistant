import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

class JarvisUI:
    def __init__(self, root):
        self.root = root
        self.root.title("JARVIS")
        self.root.geometry("600x700")

        # Chat frame
        self.chat_frame = ctk.CTkScrollableFrame(root, width=580, height=550)
        self.chat_frame.pack(pady=10)

        # Bottom input area
        bottom = ctk.CTkFrame(root)
        bottom.pack(fill="x", pady=10)

        # Entry
        self.entry = ctk.CTkEntry(bottom, placeholder_text="Type your command...")
        self.entry.pack(side="left", fill="x", expand=True, padx=10)

        # Send button
        self.send_btn = ctk.CTkButton(bottom, text="➤")
        self.send_btn.pack(side="left", padx=5)

        # Mic button
        self.mic_btn = ctk.CTkButton(bottom, text="🎤")
        self.mic_btn.pack(side="left", padx=5)

    def add_message(self, text, sender="user"):
        bubble = ctk.CTkLabel(
            self.chat_frame,
            text=text,
            wraplength=400,
            justify="left",
            corner_radius=10,
            fg_color="#1f6aa5" if sender == "user" else "#333333"
        )

        bubble.pack(anchor="e" if sender == "user" else "w", padx=10, pady=5)

    def get_input(self):
        return self.entry.get()

    def clear_input(self):
        self.entry.delete(0, "end")