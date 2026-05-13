from datetime import datetime, timedelta
import re

def parse_date_range(date_info: str):
    """
    Convert natural language date to (start_date, end_date) in YYYYMMDD format.
    Simplified version for demonstration.
    """
    now = datetime.now()
    end_date = now.strftime("%Y%m%d")
    # 기본값: 날짜 언급이 없으면 최근 1년치 데이터 조회 (2000년 방지)
    start_date = (now - timedelta(days=365)).strftime("%Y%m%d")
    
    if not date_info:
        return start_date, end_date

    # Example: "최근 6개월" (Last 6 months)
    match_months = re.search(r"(\d+)개월", date_info)
    if match_months:
        months = int(match_months.group(1))
        start_date = (now - timedelta(days=months * 30)).strftime("%Y%m%d")
        return start_date, end_date

    # Example: "2024년 1월" or just "1월"
    match_year_month = re.search(r"(\d{4})년\s*(\d{1,2})월", date_info)
    match_only_month = re.search(r"(\d{1,2})월", date_info)
    
    if match_year_month:
        year = match_year_month.group(1)
        month = match_year_month.group(2).zfill(2)
        start_date = f"{year}{month}01"
        end_date = f"{year}{month}31"
        return start_date, end_date
    elif match_only_month:
        target_month = int(match_only_month.group(1))
        current_year = now.year
        current_month = now.month
        
        # 만약 요청한 월이 현재 월보다 크거나 같으면 (아직 지나지 않았으면) 작년 데이터 조회
        if target_month >= current_month:
            year = current_year - 1
        else:
            year = current_year
            
        month_str = str(target_month).zfill(2)
        start_date = f"{year}{month_str}01"
        end_date = f"{year}{month_str}31"
        return start_date, end_date

    return start_date, end_date
