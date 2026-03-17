import streamlit as st
import sys

# --- 0. 환경 결함 방어 로직 ---
try:
    import pandas as pd
except Exception as e:
    # Pandas 바이너리 충돌(interval.pyx) 발생 시 UI에 해결책 표시
    st.error("### 🚨 라이브러리 구동 에러")
    st.warning("Pandas 라이브러리 파일이 손상되었거나 현재 시스템 환경과 맞지 않습니다.")
    st.info("아래 명령어를 복사하여 터미널(CMD)에 입력하고 엔터를 눌러주세요.")
    st.code("pip install --no-cache-dir --force-reinstall pandas numpy openpyxl", language="bash")
    st.exception(e)
    st.stop()

# --- 1. 페이지 및 스타일 설정 ---
st.set_page_config(page_title="근태 누적 분석 시스템", layout="wide", page_icon="🕐")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
    .metric-container { background: #f8f9fa; padding: 15px; border-radius: 10px; border-left: 5px solid #3498db; margin-bottom: 10px; }
    .metric-label { font-size: 14px; color: #555; }
    .metric-value { font-size: 24px; font-weight: bold; color: #2c3e50; }
</style>
""", unsafe_allow_html=True)

st.title("🗄️ 월간 근태 누적 분석 시스템")
st.info("파일을 업로드하면 기존 데이터와 합쳐지며, 동일 날짜/이름 데이터는 최신 파일 기준으로 업데이트됩니다.")

# --- 2. 초기 세션 상태 설정 ---
if 'all_data' not in st.session_state:
    st.session_state['all_data'] = pd.DataFrame()

# 제외 설정 (기본 명단 및 직급 키워드)
EXCLUDE_NAMES = ['김기돈', '임덕상', '여기대', '김효정', '김운철', '윤희주']
EXCLUDE_KEYWORDS = ['사장', '이사', '대표', '본부장']

# --- 3. 사이드바 제어 ---
with st.sidebar:
    st.header("⚙️ 관리 메뉴")
    if st.button("🔄 누적 데이터 초기화", use_container_width=True):
        st.session_state['all_data'] = pd.DataFrame()
        st.rerun()
    
    st.write("---")
    st.subheader("💡 필터링 정보")
    st.caption(f"**제외 명단:** {', '.join(EXCLUDE_NAMES)}")
    st.caption(f"**제외 키워드:** {', '.join(EXCLUDE_KEYWORDS)}")
    
    if not st.session_state['all_data'].empty:
        st.success(f"현재 누적 데이터: {len(st.session_state['all_data'])}행")

# --- 4. 파일 처리 로직 ---
uploaded_file = st.file_uploader("근태 파일(XLS, XLSX, CSV) 업로드", type=['csv', 'xls', 'xlsx'])

if uploaded_file:
    try:
        # 파일 타입별 엔진 최적화
        if uploaded_file.name.lower().endswith('.csv'):
            new_df = pd.read_csv(uploaded_file, encoding='cp949')
        elif uploaded_file.name.lower().endswith('.xls'):
            new_df = pd.read_excel(uploaded_file, engine='xlrd')
        else:
            # .xlsx 파일은 가장 안정적인 openpyxl 사용
            new_df = pd.read_excel(uploaded_file, engine='openpyxl')

        # 데이터 전처리 및 클리닝
        # 분석에 필요한 필수 컬럼들 정제
        target_cols = ['성명', '부서', '직급', '출근시각', '퇴근시각', '근무일자']
        for col in target_cols:
            if col in new_df.columns:
                new_df[col] = new_df[col].astype(str).str.strip().replace(['nan', 'None', ':', 'nan:nan', 'nan:nan:nan'], '')

        # 데이터 합치기 및 중복 제거 (근무일자 + 성명 기준)
        if st.session_state['all_data'].empty:
            st.session_state['all_data'] = new_df
        else:
            combined = pd.concat([st.session_state['all_data'], new_df], ignore_index=True)
            # drop_duplicates의 subset에 컬럼 존재 확인 후 실행
            key_cols = [c for c in ['근무일자', '성명'] if c in combined.columns]
            if key_cols:
                st.session_state['all_data'] = combined.drop_duplicates(subset=key_cols, keep='last')
            else:
                st.session_state['all_data'] = combined
            
        st.toast(f"✅ {uploaded_file.name} 업로드 성공!", icon="✅")

    except Exception as e:
        st.error(f"⚠️ 파일 분석 오류: {e}")
        st.info("파일 형식이 맞는지, 혹은 엑셀 엔진(openpyxl)이 설치되었는지 확인하세요.")

# --- 5. 분석 및 결과 출력 ---
if not st.session_state['all_data'].empty:
    df = st.session_state['all_data']
    
    # 월 정보 추출 (A열 근무일자 기준)
    target_month = "분석"
    if '근무일자' in df.columns and not df['근무일자'].empty:
        valid_dates = df['근무일자'][df['근무일자'].str.contains(r'\d', na=False)]
        if not valid_dates.empty:
            sample_date = str(valid_dates.iloc[-1])
            if '.' in sample_date:
                target_month = sample_date.split('.')[1] + "월"

    # 분석 결과 저장 딕셔너리
    results = {"출근 누락": [], "퇴근 누락": [], "연차상신 누락": [], "지각(10:01↑)": []}

    for _, row in df.iterrows():
        name = row.get('성명', '')
        dept = row.get('부서', '')
        rank = row.get('직급', '')
        date = row.get('근무일자', '')
        in_t = row.get('출근시각', '')
        out_t = row.get('퇴근시각', '')

        # [제외 필터] 이름 + 직급 + 부서 키워드
        is_excluded = (name in EXCLUDE_NAMES) or \
                      any(k in str(rank) for k in EXCLUDE_KEYWORDS) or \
                      any(k in str(dept) for k in EXCLUDE_KEYWORDS)
        
        if is_excluded or not name:
            continue

        # 이상 내역 분류 로직
        if not in_t and not out_t:
            results["연차상신 누락"].append([date, name, dept, "-", "-", "기록 없음"])
        elif not in_t and out_t:
            results["출근 누락"].append([date, name, dept, "-", out_t, "퇴근만 기록"])
        elif in_t and not out_t:
            results["퇴근 누락"].append([date, name, dept, in_t, "-", "출근만 기록"])
        elif in_t and ':' in in_t:
            try:
                # 10:01부터 지각 처리
                parts = in_t.split(':')
                h, m = int(parts[0]), int(parts[1])
                if (h == 10 and m > 0) or h > 10:
                    results["지각(10:01↑)"].append([date, name, dept, in_t, out_t, f"{in_t} 출근"])
            except: pass

    # --- 대시보드 출력 ---
    st.markdown(f"### 📊 {target_month} 근태 분석 결과 (누적)")
    
    # 요약 카드 섹션
    summary_cols = st.columns(4)
    for i, (cat, data) in enumerate(results.items()):
        unique_p = len(set([d[1] for d in data]))
        with summary_cols[i]:
            st.markdown(f"""
            <div class="metric-container">
                <div class="metric-label">{cat}</div>
                <div class="metric-value">{unique_p}명 <span style="font-size:15px; font-weight:normal;">({len(data)}건)</span></div>
            </div>
            """, unsafe_allow_html=True)

    # 상세 데이터 섹션
    st.divider()
    tab1, tab2, tab3, tab4 = st.tabs(list(results.keys()))
    tabs = [tab1, tab2, tab3, tab4]
    
    summary_text = f"### {target_month} 근태 분석 요약 (누적 결과)\n\n"

    for i, (category, data) in enumerate(results.items()):
        with tabs[i]:
            if data:
                res_df = pd.DataFrame(data, columns=['날짜', '성명', '부서', '출근', '퇴근', '비고']).sort_values(by='날짜')
                st.dataframe(res_df, use_container_width=True, hide_index=True)
                
                # 보고서용 텍스트 생성 (날짜에서 일자만 추출)
                names_list = [f"{d[1]}({str(d[0]).split('.')[-1] if '.' in str(d[0]) else d[0]}일)" for d in data]
                summary_text += f"* **{category}** : {len(set([d[1] for d in data]))}명/{len(data)}건\n    * {', '.join(names_list)}\n"
            else:
                st.success(f"✅ {category} 내역이 없습니다.")

    # 보고서 텍스트 영역
    st.divider()
    st.subheader(f"📝 {target_month} 보고서용 텍스트")
    st.text_area("하단의 내용을 복사하여 보고서에 활용하세요.", value=summary_text, height=300)

else:
    st.warning("데이터가 없습니다. 파일을 업로드해 주세요.")
