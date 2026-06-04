# 🎵 Discord Music Bot

บอทเปิดเพลง Discord ที่สร้างด้วย Python + discord.py + yt-dlp

---

## ⚙️ การติดตั้ง

### 1. ติดตั้ง Python (3.8+)
ดาวน์โหลดได้ที่ https://python.org

### 2. ติดตั้ง FFmpeg
- **Windows**: ดาวน์โหลดที่ https://ffmpeg.org/download.html แล้วเพิ่มลง PATH
- **Mac**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

### 3. ติดตั้ง Dependencies
```bash
pip install -r requirements.txt
```

### 4. สร้าง Discord Bot
1. ไปที่ https://discord.com/developers/applications
2. กด **New Application** → ตั้งชื่อ
3. ไปที่ **Bot** → กด **Add Bot**
4. เปิด **MESSAGE CONTENT INTENT** และ **SERVER MEMBERS INTENT**
5. คัดลอก **Token**

### 5. ใส่ Token
เปิดไฟล์ `bot.py` แล้วแก้บรรทัดนี้:
```python
TOKEN = "ใส่ TOKEN ของคุณที่นี่"
```

### 6. เชิญบอทเข้า Server
ไปที่ **OAuth2 → URL Generator**
- เลือก: `bot`
- เลือก permissions: `Connect`, `Speak`, `Send Messages`, `Embed Links`, `Read Message History`
- คัดลอก URL แล้วเปิดในเบราว์เซอร์

### 7. รันบอท
```bash
python bot.py
```

---

## 🎮 คำสั่งทั้งหมด

| คำสั่ง | ทางเลือก | คำอธิบาย |
|--------|----------|----------|
| `!play <เพลง/URL>` | `!p`, `!เล่น` | เล่นเพลงจาก YouTube |
| `!pause` | `!หยุด` | หยุดชั่วคราว |
| `!resume` | `!เล่นต่อ` | เล่นต่อ |
| `!skip` | `!s`, `!ข้าม` | ข้ามเพลง |
| `!stop` | `!หยุดเลย` | หยุดเล่นและล้าง Queue |
| `!queue` | `!q`, `!คิว` | ดู Queue |
| `!nowplaying` | `!np`, `!กำลังเล่น` | ดูเพลงที่กำลังเล่น |
| `!volume <0-100>` | `!vol`, `!เสียง` | ปรับระดับเสียง |
| `!clear` | `!ล้างคิว` | ล้าง Queue |
| `!join` | `!j`, `!เข้ามา` | เข้า Voice Channel |
| `!leave` | `!ออก`, `!dc` | ออกจาก Voice Channel |

---

## 💡 ตัวอย่างการใช้งาน

```
!play เพลงไทยฮิต
!play https://www.youtube.com/watch?v=...
!play playlist URL ของ YouTube
!q
!skip
!volume 80
```

---

## ❓ แก้ปัญหา

- **"opus" error** → ติดตั้ง `pip install PyNaCl`
- **ไม่มีเสียง** → ตรวจสอบว่าติดตั้ง FFmpeg แล้ว
- **บอทไม่ตอบ** → เปิด MESSAGE CONTENT INTENT ใน Discord Developer Portal
