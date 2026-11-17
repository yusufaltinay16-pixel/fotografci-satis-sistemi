FOTOGRAFÇI SATIŞ VE HAKEDİŞ SİSTEMİ - İLK SÜRÜM

ÖZELLİKLER
- Yönetici ve satıcı girişi
- Satış kaydı: satıcı, adet, tutar, TL/USD/EUR, nakit/kart/IBAN
- USD/EUR için yöneticinin tarih bazında girdiği kur
- Satıcı komisyon yüzdesi
- Genel masraf kaydı (satıcı hakedişinden düşmez)
- Satıcı ödemesi kaydı
- Tarih aralıklı rapor ve hesap kesimi
- Telefon ve bilgisayar tarayıcısına uyumlu arayüz

İLK YÖNETİCİ GİRİŞİ
Kullanıcı adı: admin
Şifre: Admin123!

İlk girişten sonra güvenlik için yönetici şifresini değiştirin.
İlk girişten sonra üst menüdeki Şifre değiştir bölümünden şifrenizi değiştirin.

WINDOWS'TA DENEME
1) Python 3.10 veya üzeri kurulu olmalı.
2) Klasörde terminal açın:
   pip install -r requirements.txt
   python app.py
3) Tarayıcıda http://127.0.0.1:5000 açın.

İNTERNETTEN TELEFONLA KULLANIM
Render için render.yaml hazırdır. Projeyi GitHub'a yükleyip Render'da Blueprint olarak bağlayın.
Render'da kalıcı disk kullanılır. Yayına almadan önce SECRET_KEY değerinin gizli tutulması ve yönetici şifresinin değiştirilmesi gerekir.

ÖNEMLİ SINIRLAR
- Bu, çalıştırılabilir ilk temel sürümdür; gerçek satışa başlamadan önce test edilmelidir.
- Yönetici satış paneli 15 saniyede bir otomatik yenilenir. Telefonun ekranına push bildirimi (uygulama kapalıyken uyarı) bu ilk sürümde etkin değildir. Gerçek push bildirimi için ayrıca servis ve anahtar kurulumu gerekir.
- Kart komisyonu/kur farkı gibi ek masraflar henüz otomatik hesaplanmaz; genel masraf olarak girilir.
- Satışlar kaydedildiği andaki kur ve yüzdeyi saklar; sonradan kur/yüzde değişikliği eski satışları değiştirmez.
- Bu sürümde hesap kesimi rapor kaydı oluşturur; kayıt kilitleme ve ayrıntılı denetim izi sonraki geliştirmedir.
