#!/usr/bin/env python3
"""
ตรวจสอบสถานะปัจจุบันของ UPS และวิเคราะห์ response
"""

import requests
import json
import sys
from datetime import datetime

def check_ups_status():
    """ตรวจสอบสถานะ UPS ปัจจุบัน"""
    
    print("🔍 ตรวจสอบสถานะ UPS ปัจจุบัน")
    print("=" * 50)
    
    base_url = "http://localhost:8000"
    
    # ทดสอบ Health Check ก่อน
    try:
        health_response = requests.get(f"{base_url}/health", timeout=5)
        if health_response.status_code == 200:
            print("✅ API Server ทำงานปกติ")
        else:
            print(f"⚠️  API Server ตอบกลับ Status: {health_response.status_code}")
    except Exception as e:
        print(f"❌ ไม่สามารถเชื่อมต่อ API Server: {e}")
        print("กรุณาตรวจสอบว่าเซอร์วิสทำงานอยู่หรือไม่:")
        print("  uvicorn app.main:app --reload")
        return False
    
    # ดึงข้อมูล UPS ทั้งหมด
    try:
        print(f"\n🔌 ดึงข้อมูล UPS ทั้งหมด...")
        ups_response = requests.get(f"{base_url}/api/ups", timeout=30)
        
        if ups_response.status_code != 200:
            print(f"❌ API ตอบกลับ Status: {ups_response.status_code}")
            print(f"Response: {ups_response.text}")
            return False
        
        data = ups_response.json()
        
        print(f"✅ ดึงข้อมูลสำเร็จ")
        print(f"📊 จำนวน UPS ทั้งหมด: {data.get('count', 0)}")
        print(f"📊 ดึงข้อมูลสำเร็จ: {data.get('success_count', 0)}")
        
        # วิเคราะห์สถานะแต่ละเครื่อง
        items = data.get('items', [])
        
        print(f"\n📋 รายละเอียดสถานะ UPS:")
        print("-" * 50)
        
        status_summary = {}
        power_fail_devices = []
        
        for item in items:
            ups_id = item.get('id', 'Unknown')
            ip = item.get('ip', 'Unknown')
            status = item.get('status', 'Unknown')
            location = item.get('location', 'Unknown')
            
            # นับสถานะ
            status_summary[status] = status_summary.get(status, 0) + 1
            
            # แสดงข้อมูลพื้นฐาน
            print(f"🔌 {ups_id} ({ip})")
            print(f"   📍 สถานที่: {location}")
            print(f"   📊 สถานะ: {status}")
            
            # ถ้าเป็น PowerFail ให้แสดงรายละเอียดเพิ่มเติม
            if status == "PowerFail":
                power_fail_devices.append(item)
                input_data = item.get('input', {})
                output_data = item.get('output', {})
                battery = item.get('batteryPercent', 0)
                
                print(f"   ⚡ แรงดันไฟเข้า: L1={input_data.get('L1V', 0)}V, L2={input_data.get('L2V', 0)}V, L3={input_data.get('L3V', 0)}V")
                print(f"   🔋 แรงดันไฟออก: L1={output_data.get('L1V', 0)}V, L2={output_data.get('L2V', 0)}V, L3={output_data.get('L3V', 0)}V")
                print(f"   🔋 แบตเตอรี่: {battery}%")
            
            # ถ้าเป็น Error ให้แสดงข้อผิดพลาด
            elif status == "error":
                error_msg = item.get('error', 'Unknown error')
                print(f"   💥 ข้อผิดพลาด: {error_msg}")
            
            print()
        
        # สรุปสถานะ
        print("📊 สรุปสถานะทั้งหมด:")
        for status, count in status_summary.items():
            emoji = {
                "Online": "🟢",
                "PowerFail": "🟡", 
                "Offline": "🔴",
                "error": "💥"
            }.get(status, "❓")
            print(f"   {emoji} {status}: {count} เครื่อง")
        
        # รายละเอียดเครื่องที่ไฟตก
        if power_fail_devices:
            print(f"\n🚨 รายละเอียดเครื่องที่ไฟตก ({len(power_fail_devices)} เครื่อง):")
            print("-" * 50)
            
            for device in power_fail_devices:
                print(f"📍 {device.get('location', 'Unknown')}")
                print(f"🔌 IP: {device.get('ip', 'Unknown')}")
                
                input_data = device.get('input', {})
                l1v = input_data.get('L1V', 0)
                
                if l1v == 0:
                    print(f"⚡ สาเหตุ: powerCut สนิท (Input = 0V)")
                elif 1 <= l1v <= 179:
                    print(f"⚡ สาเหตุ: ไฟตก (Input = {l1v}V)")
                else:
                    print(f"⚡ สาเหตุ: ไม่ทราบ (Input = {l1v}V)")
                
                battery = device.get('batteryPercent', 0)
                backup_time = device.get('backupTimeMin', 0)
                print(f"🔋 แบตเตอรี่: {battery}% (เหลือ {backup_time} นาที)")
                print()
        
        return True
        
    except Exception as e:
        print(f"💥 เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
        return False

def check_specific_ups(ip):
    """ตรวจสอบ UPS เครื่องเดียว"""
    
    print(f"🔍 ตรวจสอบ UPS {ip}")
    print("-" * 30)
    
    try:
        response = requests.get(f"http://localhost:8000/api/ups/{ip}", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ ดึงข้อมูลสำเร็จ")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return True
        else:
            print(f"❌ API ตอบกลับ Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"💥 เกิดข้อผิดพลาด: {e}")
        return False

def main():
    """ฟังก์ชันหลัก"""
    
    if len(sys.argv) > 1:
        # ตรวจสอบ UPS เครื่องเดียว
        ip = sys.argv[1]
        check_specific_ups(ip)
    else:
        # ตรวจสอบทั้งหมด
        success = check_ups_status()
        
        if success:
            print("\n💡 คำแนะนำ:")
            print("- หากยังพบปัญหาไฟตก ให้ตรวจสอบค่าแรงดันจริงจาก SNMP")
            print("- ใช้คำสั่ง: python check_current_status.py <IP> เพื่อดูเครื่องเดียว")
            print("- ตรวจสอบ log: tail -f ups_dashboard.log")
        
        sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()