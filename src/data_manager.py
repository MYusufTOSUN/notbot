"""
Veri Yönetim Modülü
Notları saklar, karşılaştırır ve değişiklikleri tespit eder.
Desteklenen depolama: Lokal JSON, JSONBin.io, GitHub API
"""

import json
import base64
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
from src.config import (
    GRADES_FILE, JSONBIN_API_KEY, JSONBIN_BIN_ID,
    GITHUB_TOKEN, GITHUB_REPO, get_storage_mode
)
from src.logger import log_info, log_error, log_debug, log_warning


class DataManager:
    """Not verilerini yöneten sınıf."""
    
    def __init__(self):
        self.storage_mode = get_storage_mode()
        self.grades_file = GRADES_FILE
        log_info(f"Depolama modu: {self.storage_mode}")
    
    def load_grades(self) -> Dict:
        """
        Kaydedilmiş notları yükle.
        
        Returns:
            Notlar sözlüğü: {"ders_adi": {"not": "XX", "tarih": "..."}, ...}
        """
        if self.storage_mode == "jsonbin":
            return self._load_from_jsonbin()
        elif self.storage_mode == "github":
            return self._load_from_github()
        else:
            return self._load_from_local()
    
    def save_grades(self, grades: Dict) -> bool:
        """
        Notları kaydet.
        
        Args:
            grades: Notlar sözlüğü
            
        Returns:
            Başarılı ise True
        """
        # Zaman damgası ekle
        grades["_last_updated"] = datetime.now().isoformat()
        
        if self.storage_mode == "jsonbin":
            return self._save_to_jsonbin(grades)
        elif self.storage_mode == "github":
            return self._save_to_github(grades)
        else:
            return self._save_to_local(grades)
    
    def compare_grades(self, old_grades: Dict, new_grades: Dict) -> List[Dict]:
        """
        Eski ve yeni notları karşılaştır.
        
        Args:
            old_grades: Önceki notlar
            new_grades: Güncel notlar
            
        Returns:
            Değişiklik listesi: [{
                "course": str, 
                "field": str,  # Değişen alan (vize1, final, harf, vs.)
                "old_value": str, 
                "new_value": str
            }, ...]
        """
        changes = []
        
        # Meta verileri atla
        skip_keys = ["_last_updated", "_version"]
        
        # İzlenecek önemli alanlar (öncelik sırasına göre)
        tracked_fields = ["harf", "gn", "final", "but", "vize1", "vize2", "vize3", "vize4", "durum"]
        
        for course, grade_info in new_grades.items():
            if course in skip_keys:
                continue
            
            if not isinstance(grade_info, dict):
                continue
            
            # Ders adını al
            ders_adi = grade_info.get("ders_adi", course)
            
            if course not in old_grades:
                # Yeni ders eklendi
                changes.append({
                    "course": ders_adi,
                    "field": "yeni_ders",
                    "grade_info": grade_info,  # Tüm not bilgilerini ekle
                    "old_value": None,
                    "new_value": "Yeni ders"
                })
                log_info(f"Yeni ders tespit edildi: {ders_adi}")
                    
            else:
                old_grade_info = old_grades[course]
                if not isinstance(old_grade_info, dict):
                    old_grade_info = {}
                
                # Her alan için değişiklik kontrolü
                has_change = False
                for field in tracked_fields:
                    new_value = grade_info.get(field, "").strip()
                    old_value = old_grade_info.get(field, "").strip()
                    
                    # Boş olmayan yeni değer var ve eskiden farklıysa
                    if new_value and new_value != old_value:
                        has_change = True
                        log_info(f"Not değişikliği: {ders_adi} - {field}: {old_value or 'boş'} -> {new_value}")
                
                # Değişiklik varsa tek bir kayıt ekle (tüm bilgilerle)
                if has_change:
                    changes.append({
                        "course": ders_adi,
                        "field": "güncelleme",
                        "grade_info": grade_info,  # Tüm not bilgilerini ekle
                        "old_value": None,
                        "new_value": "Güncellendi"
                    })
        
        if not changes:
            log_debug("Notlarda değişiklik yok")
        
        return changes
    
    # ===== Lokal Depolama =====
    
    def _load_from_local(self) -> Dict:
        """Lokal JSON dosyasından yükle."""
        try:
            if self.grades_file.exists():
                with open(self.grades_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    log_debug(f"Lokal dosyadan {len(data)} öğe yüklendi")
                    return data
            else:
                log_debug("Lokal dosya bulunamadı, boş sözlük döndürülüyor")
                return {}
        except json.JSONDecodeError as e:
            log_error(f"JSON parse hatası: {e}")
            return {}
        except Exception as e:
            log_error(f"Lokal yükleme hatası: {e}")
            return {}
    
    def _save_to_local(self, grades: Dict) -> bool:
        """Lokal JSON dosyasına kaydet."""
        try:
            self.grades_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.grades_file, "w", encoding="utf-8") as f:
                json.dump(grades, f, ensure_ascii=False, indent=2)
            log_debug(f"Veriler lokale kaydedildi: {self.grades_file}")
            return True
        except Exception as e:
            log_error(f"Lokal kaydetme hatası: {e}")
            return False
    
    # ===== JSONBin.io Depolama =====
    
    def _load_from_jsonbin(self) -> Dict:
        """JSONBin.io'dan yükle."""
        try:
            url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}/latest"
            headers = {
                "X-Master-Key": JSONBIN_API_KEY,
                "X-Bin-Meta": "false"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                log_debug(f"JSONBin'den {len(data)} öğe yüklendi")
                return data
            else:
                log_warning(f"JSONBin yükleme hatası: {response.status_code}")
                return {}
                
        except requests.RequestException as e:
            log_error(f"JSONBin bağlantı hatası: {e}")
            return {}
    
    def _save_to_jsonbin(self, grades: Dict) -> bool:
        """JSONBin.io'ya kaydet."""
        try:
            url = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"
            headers = {
                "Content-Type": "application/json",
                "X-Master-Key": JSONBIN_API_KEY
            }
            
            response = requests.put(
                url,
                json=grades,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                log_debug("Veriler JSONBin'e kaydedildi")
                return True
            else:
                log_error(f"JSONBin kaydetme hatası: {response.status_code}")
                return False
                
        except requests.RequestException as e:
            log_error(f"JSONBin bağlantı hatası: {e}")
            return False
    
    # ===== GitHub API Depolama =====
    
    def _load_from_github(self) -> Dict:
        """GitHub reposundan yükle."""
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/notlar.json"
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                content = response.json()
                decoded = base64.b64decode(content["content"]).decode("utf-8")
                data = json.loads(decoded)
                self._github_sha = content["sha"]  # Güncelleme için SHA'yı sakla
                log_debug(f"GitHub'dan {len(data)} öğe yüklendi")
                return data
            elif response.status_code == 404:
                log_debug("GitHub'da dosya bulunamadı")
                self._github_sha = None
                return {}
            else:
                log_warning(f"GitHub yükleme hatası: {response.status_code}")
                return {}
                
        except requests.RequestException as e:
            log_error(f"GitHub bağlantı hatası: {e}")
            return {}
    
    def _save_to_github(self, grades: Dict) -> bool:
        """GitHub reposuna kaydet."""
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/notlar.json"
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            content = json.dumps(grades, ensure_ascii=False, indent=2)
            encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            
            data = {
                "message": f"Not güncelleme - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "content": encoded
            }
            
            # Mevcut dosya varsa SHA ekle
            if hasattr(self, "_github_sha") and self._github_sha:
                data["sha"] = self._github_sha
            
            response = requests.put(url, json=data, headers=headers, timeout=10)
            
            if response.status_code in [200, 201]:
                log_debug("Veriler GitHub'a kaydedildi")
                return True
            else:
                log_error(f"GitHub kaydetme hatası: {response.status_code}")
                return False
                
        except requests.RequestException as e:
            log_error(f"GitHub bağlantı hatası: {e}")
            return False


def get_data_manager() -> DataManager:
    """Global DataManager instance döndür."""
    return DataManager()
