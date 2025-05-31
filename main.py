import streamlit as st
import calendar
import time
import re
import pandas as pd
import plotly.graph_objects as go
import uuid
import gspread
from datetime import datetime
from google.oauth2 import service_account
#from storage_module import get_df, save_df

#google sheet 初始化
SHEET_NAME = "meeting_records"
secrets = st.secrets["gspread"]
credentials = service_account.Credentials.from_service_account_info(secrets)
scoped_credentials = credentials.with_scopes([
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
])
client = gspread.authorize(scoped_credentials)
sheet = client.open(SHEET_NAME).sheet1

@st.cache_data(ttl=60)


def register_user(user_id, password):
    user_id, password = str(user_id), str(password)
    if len(password) < 6 or not re.search(r'[A-Za-z]', password):
        return False, "密碼必須至少 6 個字元，且包含英文字母"
    df = get_df()
    if user_id in df['user_id'].values:
        return False, "使用者 ID 已存在"
    new_entry = pd.DataFrame([{
        'user_id': user_id,
        'password': password,
        'available_dates': '',
        'friends': '',
        'friend_requests': ''
    }])
    df = pd.concat([df, new_entry], ignore_index=True)
    save_df(df)
    return True, "註冊成功"

def authenticate_user(user_id, password):
    df = get_df()
    return not df[(df['user_id'] == str(user_id)) & (df['password'] == str(password))].empty

def update_availability(user_id, available_dates):
    df = get_df()
    date_str = ','.join(available_dates)
    df.loc[df['user_id'] == user_id, 'available_dates'] = date_str
    save_df(df)
    return date_str

def display_calendar_view(user_id):
    today = datetime.today()
    now = time.time()

    # 狀態 key 命名
    year_key = f"{user_id}_show_year"
    month_key = f"{user_id}_show_month"
    last_click_key = f"{user_id}_last_click"
    last_user_key = "last_display_user"

    # 初始化
    if last_user_key not in st.session_state or st.session_state[last_user_key] != user_id:
        st.session_state[year_key] = today.year
        st.session_state[month_key] = today.month
        st.session_state[last_click_key] = 0.0
        st.session_state[last_user_key] = user_id

    # 防止多次快速點擊
    can_click = now - st.session_state[last_click_key] > 1.0

    # 月份控制
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("← 上一個月", key=f"prev_btn_{user_id}") and can_click:
            st.session_state[last_click_key] = now
            if st.session_state[month_key] == 1:
                st.session_state[month_key] = 12
                st.session_state[year_key] -= 1
            else:
                st.session_state[month_key] -= 1
    with col3:
        if st.button("下一個月 →", key=f"next_btn_{user_id}") and can_click:
            st.session_state[last_click_key] = now
            if st.session_state[month_key] == 12:
                st.session_state[month_key] = 1
                st.session_state[year_key] += 1
            else:
                st.session_state[month_key] += 1

    year = st.session_state[year_key]
    month = st.session_state[month_key]

    # 資料抓取與檢查
    df = get_df()
    user_data = df[df["user_id"] == user_id]
    if user_data.empty:
        st.warning(f"{user_id} 無資料")
        return

    available_raw = user_data.iloc[0].get("available_dates", "")
    if not isinstance(available_raw, str):
        available_raw = ""
    available = set(d.strip() for d in available_raw.split(",") if d.strip())

    cal = calendar.Calendar(firstweekday=0)
    month_days = list(cal.itermonthdays(year, month))

    week_headers = ['一', '二', '三', '四', '五', '六', '日']
    table = "<table style='border-collapse: collapse; width: 100%; text-align: center;'>"
    table += f"<caption style='text-align:center; font-weight:bold; padding: 8px'>{year} 年 {month} 月</caption>"
    table += "<tr>" + "".join(f"<th>{d}</th>" for d in week_headers) + "</tr><tr>"

    day_counter = 0
    for day in month_days:
        if day == 0:
            table += "<td></td>"
        else:
            date_str = f"{year}-{month:02d}-{day:02d}"
            if date_str in available:
                table += f"<td style='background-color:#b2fab4;border:1px solid #ccc;padding:5px'>{day}</td>"
            else:
                table += f"<td style='border:1px solid #ccc;padding:5px;color:#ccc'>{day}</td>"
        day_counter += 1
        if day_counter % 7 == 0:
            table += "</tr><tr>"
    table += "</tr></table>"

    st.markdown(table, unsafe_allow_html=True)

def find_users_by_date(date, current_user_id):
    df = get_df()
    return df[(df['available_dates'].str.contains(date, na=False)) & 
              (df['user_id'] != current_user_id)]['user_id'].tolist()

def confirm_action(label, key=None, warn_text="此動作不可復原，請再次確認！"):
    st.markdown(
        f"<div style='color:white;background:#d9534f;padding:8px 16px;margin:8px 0;border-radius:5px;'>"
        f"<b>安全性警告：</b>{warn_text}"
        f"</div>", unsafe_allow_html=True
    )
    confirmed = st.checkbox("我已充分閱讀、確認並願意執行此不可逆動作", key=f"{key}_checkbox")
    do_action = st.button(label, key=f"{key}_btn")
    return confirmed and do_action

def send_friend_request(current_user, target_user):
    if current_user == target_user:
        return "不能傳送好友申請給自己"

    df = get_df()

    if target_user not in df["user_id"].values:
        return "該使用者不存在"

    curr_friends_raw = df.loc[df["user_id"] == current_user, "friends"].values[0]
    curr_friends_set = set(f.strip() for f in curr_friends_raw.split(",") if f.strip())

    if target_user in curr_friends_set:
        return "對方已經是你的好友"

    target_requests = df.loc[df["user_id"] == target_user, "friend_requests"].values[0]
    target_requests_set = set(target_requests.split(",")) if target_requests else set()

    if current_user in target_requests_set:
        return "已送出好友申請 請等待對方回應"

    target_requests_set.add(current_user)
    df.loc[df["user_id"] == target_user, "friend_requests"] = ",".join(sorted(target_requests_set))
    save_df(df)
    return "好友申請已送出"

def accept_friend_request(user_id, requester):
    df = get_df()
    idx = df[df['user_id'] == user_id].index[0]
    friends = set(df.at[idx, 'friends'].split(',')) if df.at[idx, 'friends'] else set()
    friends.add(requester)
    df.at[idx, 'friends'] = ','.join(sorted(friends))

    req_idx = df[df['user_id'] == requester].index[0]
    req_friends = set(df.at[req_idx, 'friends'].split(',')) if df.at[req_idx, 'friends'] else set()
    req_friends.add(user_id)
    df.at[req_idx, 'friends'] = ','.join(sorted(req_friends))

    requests = set(df.at[idx, 'friend_requests'].split(',')) if df.at[idx, 'friend_requests'] else set()
    requests.discard(requester)
    df.at[idx, 'friend_requests'] = ','.join(sorted(requests))

    save_df(df)
    return "您已與對方成為好友"

def reject_friend_request(user_id, requester):
    df = get_df()
    idx = df[df['user_id'] == user_id].index[0]
    requests = set(df.at[idx, 'friend_requests'].split(',')) if df.at[idx, 'friend_requests'] else set()
    requests.discard(requester)
    df.at[idx, 'friend_requests'] = ','.join(sorted(requests))
    save_df(df)
    return "已拒絕好友申請"

def list_friend_requests(user_id):
    df = get_df()
    user_row = df[df['user_id'] == user_id]
    if user_row.empty:
        return []   # 或直接 return None，看你前面怎麼判斷
    idx = user_row.index[0]
    requests_raw = df.at[idx, 'friend_requests']
    return [r.strip() for r in requests_raw.split(',') if r.strip()] if requests_raw else []


def list_friends(user_id):
    df = get_df()
    idx = df[df['user_id'] == user_id].index[0]
    friends = df.at[idx, 'friends']
    return sorted(list(filter(None, friends.split(','))))

def show_friends_availability(user_id):
    df = get_df()
    idx = df[df['user_id'] == user_id].index[0]
    friends = df.at[idx, 'friends']
    friends = list(filter(None, friends.split(',')))
    if not friends:
        st.info("目前尚無好友")
        return

    st.subheader("好友的空閒日期")
    if "friend_view_states" not in st.session_state:
        st.session_state.friend_view_states = {}

    today = datetime.today()
    next_30_days = [today + timedelta(days=i) for i in range(30)]
    date_labels = [d.strftime("%Y-%m-%d") for d in next_30_days]

    for friend in friends:
        if friend not in st.session_state.friend_view_states:
            st.session_state.friend_view_states[friend] = False

        with st.expander(f"{friend}", expanded=st.session_state.friend_view_states[friend]):
            friend_data = df[df['user_id'] == friend]
            if not friend_data.empty:
                dates = friend_data.iloc[0]['available_dates']
                available_set = set(d.strip() for d in dates.split(',') if d.strip())

                calendar_df = pd.DataFrame({
                    "日期": date_labels,
                    "可用": ["是" if d in available_set else "否" for d in date_labels]
                })
                st.table(calendar_df)

                fig = go.Figure(go.Bar(
                    x=date_labels,
                    y=[1 if d in available_set else 0 for d in date_labels],
                    marker_color=["green" if d in available_set else "lightgray" for d in date_labels],
                ))
                fig.update_layout(
                    title="未來可用日",
                    xaxis_title="日期",
                    yaxis=dict(showticklabels=False),
                    height=300
                )
                st.plotly_chart(fig, use_container_width=True)

def show_friend_list_with_availability(user_id):
    df = get_df()
    friends = list_friends(user_id)

    if not friends:
        st.info("您目前尚無好友")
    else:
        selected_friend = st.selectbox("選擇好友查看空閒時間", friends)

        if selected_friend:
            friend_data = df[df["user_id"] == selected_friend]

            try:
                display_calendar_view(selected_friend)
            except Exception as e:
                st.error(f"{selected_friend} 的日曆顯示失敗：{e}")

            if not friend_data.empty:
                dates = friend_data.iloc[0].get("available_dates", "")
                if not isinstance(dates, str):
                    dates = ""
                date_list = [d.strip() for d in dates.split(",") if d.strip()]
                if date_list:
                    st.markdown(f"**空閒時間**：{'、'.join(date_list)}")
                else:
                    st.info("尚未登記可用時間")
            else:
                st.warning("找不到該使用者資料")
                date_list = [d.strip() for d in dates.split(',')] if dates else []
                st.markdown(f" **空閒時間**：{'、'.join(date_list) if date_list else '尚未登記'}")

# 建立活動
def add_event_row(group_name, event_title, event_date, created_by, event_summary):
    df = get_df()
    for col in ["row_type", "activity_id", "group_name", "event_title", "event_date", "created_by", "event_summary", "participants_yes", "participants_no"]:
        if col not in df.columns:
            df[col] = ""
    new_row = {
        "row_type": "event",
        "activity_id": str(uuid.uuid4()),
        "group_name": group_name,
        "event_title": event_title,
        "event_date": event_date,
        "created_by": created_by,
        "event_summary": event_summary,
        "participants_yes": "",
        "participants_no": ""
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_df(df)

# 查詢活動（自動排除過期活動，並清理資料庫）
def get_event_rows(group_name=None, auto_clean=True):
    df = get_df()
    if 'row_type' not in df.columns:
        return pd.DataFrame()
    events = df[df['row_type'] == 'event']
    today_str = date.today().strftime("%Y-%m-%d")
    # 篩選群組
    if group_name is not None:
        events = events[events['group_name'] == group_name]
    # 自動移除過期活動
    if auto_clean:
        valid_idx = events[events["event_date"] >= today_str].index
        expired_idx = events[events["event_date"] < today_str].index
        if len(expired_idx) > 0:
            df = df.drop(expired_idx)
            save_df(df)
        return events.loc[valid_idx]
    else:
        return events

# 取得單一活動資料
def get_event_by_id(activity_id):
    df = get_df()
    rows = df[df['activity_id'] == activity_id]
    if rows.empty:
        return None
    return rows.iloc[0]

# 更新參加/不參加名單
def update_event_participation_by_id(activity_id, yes_list, no_list):
    df = get_df()
    idx_list = df[df['activity_id'] == activity_id].index
    if not idx_list.empty:
        idx = idx_list[0]
        df.at[idx, "participants_yes"] = ",".join(yes_list)
        df.at[idx, "participants_no"] = ",".join(no_list)
        save_df(df)

# 刪除活動
def delete_event_by_id(activity_id):
    df = get_df()
    df = df[df['activity_id'] != activity_id].reset_index(drop=True)
    save_df(df)
    return True

# UI: 活動清單渲染（for群組活動頁）
def render_group_events_ui(group_name, user_id):
    st.subheader(f"{group_name} 群組活動")
    # 活動建立 UI
    st.markdown("### 建立新活動")
    event_title = st.text_input("活動名稱", key=f"title_{group_name}")
    event_date = st.date_input("活動日期", key=f"date_{group_name}")
    event_summary = st.text_area("活動概述", key=f"summary_{group_name}")
    if st.button("建立活動", key=f"add_{group_name}"):
        if event_title and event_date:
            add_event_row(
                group_name,
                event_title,
                event_date.strftime("%Y-%m-%d"),
                user_id,
                event_summary
            )
            st.success("活動已建立")
        else:
            st.error("活動名稱與日期必填")

    # 活動清單（自動略過過期活動）
    events_to_show = get_event_rows(group_name)
    for idx, row in events_to_show.iterrows():
        activity_id = row['activity_id']
        st.markdown(f"**活動名稱：{row['event_title']}**")
        st.markdown(f"活動日期：{row['event_date']}")
        st.markdown(f"主辦人：{row['created_by']}")
        st.markdown(f"活動說明：{row['event_summary']}")
        yes_list = [x for x in str(row['participants_yes']).split(",") if x]
        no_list = [x for x in str(row['participants_no']).split(",") if x]
        is_owner = (row['created_by'] == user_id)

        # 主辦人可取消活動與下載名單
        if is_owner:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("取消活動", key=f"cancel_{activity_id}"):
                    delete_event_by_id(activity_id)
                    st.success("活動已取消")
                    
            with c2:
                df_yes = pd.DataFrame({"user": yes_list, "status": "參加"})
                df_no = pd.DataFrame({"user": no_list, "status": "不參加"})
                df_download = pd.concat([df_yes, df_no], ignore_index=True)
                df_download.columns = ["名單", "狀態"]

                st.download_button("下載CSV", df_download.to_csv(index=False).encode("utf-8"), file_name=f"{group_name}_{row['event_title']}_名單.csv")

        # 只有沒選過的人才能選
        if user_id not in yes_list and user_id not in no_list:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("參加", key=f"join_{activity_id}"):
                    yes_list.append(user_id)
                    update_event_participation_by_id(activity_id, yes_list, no_list)
                    st.success("已標記參加")
                    
            with c2:
                if st.button("不參加", key=f"notjoin_{activity_id}"):
                    no_list.append(user_id)
                    update_event_participation_by_id(activity_id, yes_list, no_list)
                    st.success("已標記不參加")
                    
        elif user_id in yes_list:
            st.info("你已選擇參加")
            if st.button("取消參加", key=f"leave_yes_{activity_id}"):
                yes_list.remove(user_id)
                update_event_participation_by_id(activity_id, yes_list, no_list)
                st.success("已取消參加")
                
        elif user_id in no_list:
            st.info("你已選擇不參加")
            if st.button("重新選擇", key=f"leave_no_{activity_id}"):
                no_list.remove(user_id)
                update_event_participation_by_id(activity_id, yes_list, no_list)
                st.success("已取消不參加")
                

        # 展示名單
        st.write("目前參加名單")
        st.write("參加：", yes_list if yes_list else "尚無人參加")
        st.write("不參加：", no_list if no_list else "尚無人標記不參加")
        st.markdown("---")
def ensure_group_columns(df):
    if 'groups' not in df.columns:
        df['groups'] = ''
    if 'group_members' not in df.columns:
        df['group_members'] = ''
    return df

# 工具函式：解析與重組 group_members 欄位
def parse_group_members(members_str):
    group_map = {}
    if members_str:
        entries = [s for s in members_str.split('|') if s]
        for entry in entries:
            if ':' not in entry:
                continue
            group, members = entry.split(':', 1)
            member_list = [m.strip() for m in members.split(',') if m.strip()]
            group_map[group] = set(member_list)
    return group_map

def to_group_members_str(group_map):
    return ''.join(f'|{g}:{",".join(sorted(mems))}' for g, mems in group_map.items() if mems)

def create_group(user_id, group_name):
    df = get_df()
    df = ensure_group_columns(df)

    # 檢查群組名稱是否已存在
    existing_groups = set()
    for g in df["groups"].dropna():
        existing_groups.update(g.split(","))
    if group_name in existing_groups:
        return False, "該群組名稱已存在"

    # 為用戶新增群組到 groups 與 group_members
    for i in df.index:
        if df.at[i, "user_id"] == user_id:
            # 更新 groups
            groups = df.at[i, "groups"]
            group_set = set(groups.split(",")) if groups else set()
            group_set.add(group_name)
            df.at[i, "groups"] = ",".join(sorted(group_set))
            # 更新 group_members
            group_map = parse_group_members(df.at[i, "group_members"])
            group_map.setdefault(group_name, set()).add(user_id)
            df.at[i, "group_members"] = to_group_members_str(group_map)
            break

    save_df(df)
    return True, "建立群組成功"

def invite_friend_to_group(current_user, friend_id, group_name):
    df = get_df()
    df = ensure_group_columns(df)

    # 不能邀請自己
    if current_user == friend_id:
        return False, "不能邀請自己加入群組"

    # 檢查使用者是否存在
    friend_row = df[df["user_id"] == friend_id]
    if friend_row.empty:
        return False, "該使用者不存在"

    # 檢查是否為好友
    current_row = df[df["user_id"] == current_user]
    if current_row.empty:
        return False, "當前使用者不存在"
    current_friends_raw = current_row["friends"].values[0]
    current_friends = set(current_friends_raw.split(",")) if current_friends_raw else set()
    if friend_id not in current_friends:
        return False, "只能邀請好友加入群組"

    # 檢查對方是否已在群組中
    group_map = parse_group_members(friend_row["group_members"].values[0])
    if group_name in group_map and friend_id in group_map[group_name]:
        return False, "對方已經在該群組中"

    # 更新 groups 欄
    idx = friend_row.index[0]
    groups = df.at[idx, "groups"]
    group_set = set(groups.split(",")) if groups else set()
    group_set.add(group_name)
    df.at[idx, "groups"] = ",".join(sorted(group_set))

    # 更新 group_members 欄
    group_map = parse_group_members(df.at[idx, "group_members"])
    group_map.setdefault(group_name, set()).add(friend_id)
    df.at[idx, "group_members"] = to_group_members_str(group_map)

    save_df(df)
    return True, "邀請成功，好友已加入群組"

def list_groups_for_user(user_id):
    df = get_df()
    df = ensure_group_columns(df)
    idx = df[df['user_id'] == user_id].index[0]
    user_groups = set(df.at[idx, 'groups'].split(',')) if df.at[idx, 'groups'] else set()
    group_members_map = {g: [] for g in user_groups}
    for _, row in df.iterrows():
        row_groups = set(row['groups'].split(',')) if row['groups'] else set()
        for g in user_groups:
            if g in row_groups:
                group_members_map[g].append(row['user_id'])
    return group_members_map

def remove_member_from_group(user_id, group_name, target_id):
    df = get_df()
    df = ensure_group_columns(df)

    if target_id not in df['user_id'].values:
        return False, "成員不存在"

    idx = df[df['user_id'] == target_id].index[0]

    # 1. 移除 groups 欄位的群組
    group_list = set(df.at[idx, 'groups'].split(',')) if df.at[idx, 'groups'] else set()
    if group_name in group_list:
        group_list.remove(group_name)
        df.at[idx, 'groups'] = ','.join(sorted(group_list))

    # 2. 更新 group_members 欄位
    group_map = parse_group_members(df.at[idx, 'group_members'])
    if group_name in group_map:
        group_map[group_name].discard(target_id)
        if not group_map[group_name]:
            del group_map[group_name]
    df.at[idx, 'group_members'] = to_group_members_str(group_map)

    save_df(df)
    return True, f"{target_id} 已從群組 {group_name} 中移除"

def delete_group(group_name):
    df = get_df()
    df = ensure_group_columns(df)

    # 1. 先移除所有人的 groups 和 group_members 欄位中的這個群組
    for idx, row in df.iterrows():
        # 移除 groups 欄
        groups = set(row['groups'].split(',')) if row['groups'] else set()
        if group_name in groups:
            groups.remove(group_name)
            df.at[idx, 'groups'] = ','.join(sorted(groups))
        # 移除 group_members 欄
        group_map = parse_group_members(row['group_members'])
        if group_name in group_map:
            del group_map[group_name]
        df.at[idx, 'group_members'] = to_group_members_str(group_map)
    
    # 2. 刪除群組本身與所有活動（row_type==group 或 event 且 group_name符合）
    df = df[~(((df['row_type'] == 'group') | (df['row_type'] == 'event')) & (df['group_name'] == group_name))]

    save_df(df)
    return True, f"群組 {group_name} 及其活動已刪除"


def show_group_availability(group_map):
    st.subheader("群組成員空閒時間")
    if not group_map:
        st.info("你目前沒有加入任何群組")
        return
    group_names = list(group_map.keys())
    selected_group = st.selectbox("選擇群組", group_names, key="group_selector")
    members = group_map.get(selected_group, [])
    if not members:
        st.info("這個群組尚無其他成員")
        return
    selected_user = st.selectbox("選擇要查看的成員", members, key=f"user_selector_{selected_group}")
    if st.session_state.get("last_calendar_group") != selected_group or st.session_state.get("last_calendar_user") != selected_user:
        for suffix in ["show_year", "show_month", "last_click"]:
            st.session_state.pop(f"{selected_user}_{suffix}", None)
        st.session_state["last_calendar_group"] = selected_group
        st.session_state["last_calendar_user"] = selected_user
    display_calendar_view(selected_user)

def render_group_management_ui(user_id):
    st.subheader("所屬群組與成員")
    groups = list_groups_for_user(user_id)
    if not groups:
        st.info("您尚未加入任何群組")
    else:
        for gname, members in groups.items():
            st.markdown(f"#### {gname}")
            st.markdown(f"成員：{', '.join(members)}")

    st.markdown("---")
    st.subheader("建立新群組")
    new_group = st.text_input("群組名稱", key="new_group_input")
    if st.button("建立群組"):
        success, msg = create_group(user_id, new_group)
        if success:
            st.success(msg)
        else:
            st.error(msg)

    st.subheader("邀請好友加入群組")
    friend_to_invite = st.text_input("好友 ID", key="friend_invite_input")

    group_choices = list(groups.keys()) if groups else []
    if group_choices:
        group_target = st.selectbox("選擇要加入的群組", group_choices, key="group_invite_target")
        if st.button("邀請好友"):
            success, msg = invite_friend_to_group(user_id, friend_to_invite, group_target)
            st.success(msg) if success else st.error(msg)
    else:
        st.info("您目前沒有任何群組，請先建立群組才能邀請好友加入")
        
    st.markdown("---")
    st.subheader("移除群組成員")
    if groups:
        selected_group_for_kick = st.selectbox("選擇群組", list(groups.keys()), key="kick_group_select")
        kickable_members = [m for m in groups[selected_group_for_kick] if m != user_id]
        if kickable_members:
            selected_member_to_kick = st.selectbox("選擇要移除的成員", kickable_members, key="kick_member_select")
            if confirm_action("確定移除這位成員", key="remove_member", warn_text="移除後該成員將無法再存取本群組資料，且無法復原。"):
                success, msg = remove_member_from_group(user_id, selected_group_for_kick, selected_member_to_kick)
                if success:
                    st.success("移除完成")
                    st.info(msg)
                else:
                    st.error(msg)
        else:
            st.info("該群組沒有其他成員可移除")
            
    st.markdown("---")
    st.subheader("刪除群組")
    if groups:
        selected_group_for_delete = st.selectbox("選擇要刪除的群組", list(groups.keys()), key="delete_group_selector")
        if confirm_action("確定刪除這個群組", key="delete_group", warn_text="本群組及所有資料將永久刪除，無法復原！"):
            success, msg = delete_group(selected_group_for_delete)
            if success:
                st.success("刪除完成")
                st.info(msg)
            else:
                st.error(msg)

    else:
        st.info("您尚未加入任何群組")
    for gname, members in groups.items():
        st.markdown(f"#### {gname}")
        st.markdown(f"成員：{', '.join(members)}")
        with st.expander(f"【{gname}】活動／日程表"):
            render_group_events_ui(gname, user_id)

def get_df():
    records = sheet.get_all_records()
    df = pd.DataFrame(records)
    if df.empty:
        df = pd.DataFrame(columns=['row_type', 'user_id', 'password', 'available_dates', 'friends', 'friend_requests', 'groups', 'group_members', 'group_name', 'event_title', 'event_date', 'created_by', 'participants_yes', 'participants_no'])
    else:
        # 確保所有欄位齊全
        for col in ['row_type', 'user_id', 'password', 'available_dates', 'friends', 'friend_requests', 'groups', 'group_members', 'group_name', 'event_title', 'event_date', 'created_by', 'participants_yes', 'participants_no']:
            if col not in df.columns:
                df[col] = ''
        df = df.fillna("")
    return df

def save_df(df, cooldown=2.0):
    # 強制所有日期欄位為字串
    for col in df.columns:
        if df[col].dtype == 'datetime64[ns]' or df[col].dtype == 'datetime64[ns, UTC]':
            df[col] = df[col].dt.strftime('%Y-%m-%d')
        elif df[col].apply(lambda x: isinstance(x, (pd.Timestamp, datetime, date))).any():
            df[col] = df[col].apply(lambda x: x.strftime('%Y-%m-%d') if isinstance(x, (pd.Timestamp, datetime, date)) else x)

    now = time.time()
    if now - st.session_state.get("last_save_timestamp", 0) < cooldown:
        st.warning("操作太頻繁，請稍候再試")
        return False
    df = df.fillna("")
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    st.session_state.last_save_timestamp = now
    return True


# 活動資料操作輔助
def get_event_rows(group_name=None):
    df = get_df()
    events = df[df['row_type'] == 'event']
    if group_name is not None:
        events = events[events['group_name'] == group_name]
    return events

def add_event_row(group_name, event_title, event_date, created_by, event_summary):
    df = get_df()
    # 建議補欄位兼容
    for col in ["group_name", "event_title", "event_date", "created_by", "event_summary", "participants_yes", "participants_no"]:
        if col not in df.columns:
            df[col] = ""
    new_row = {
        "row_type": "event",    
        "group_name": group_name,
        "event_title": event_title,
        "event_date": event_date,
        "created_by": created_by,
        "event_summary": event_summary,
        "participants_yes": "",
        "participants_no": ""
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_df(df)


def update_event_participation(event_idx, yes_list, no_list):
    df = get_df()
    df.at[event_idx, "participants_yes"] = ",".join(yes_list)
    df.at[event_idx, "participants_no"] = ",".join(no_list)
    save_df(df)
def render_ui():
    st.title("NO_JO")

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user_id" not in st.session_state:
        st.session_state.user_id = ""
    if "page" not in st.session_state:
        st.session_state.page = "登入"
    if "rerun_triggered" not in st.session_state:
        st.session_state.rerun_triggered = False
    if (
        st.session_state.get("authenticated", False)
        and st.session_state.page == "登入成功"
        and not st.session_state.rerun_triggered
    ):
        st.session_state.page = "登記可用時間"
        st.session_state.rerun_triggered = True
        st.rerun()

    

    if st.session_state.authenticated:
        if st.session_state.user_id == "GM":
            page_options = ["登記可用時間", "查詢可配對使用者", "送出好友申請", "回應好友申請", "查看好友清單", "群組管理", "管理介面", "登出"]
        else:
            page_options = ["登記可用時間", "查詢可配對使用者", "送出好友申請", "回應好友申請", "查看好友清單", "群組管理", "登出"]
    else:
        page_options = ["登入", "註冊"]

    selected_page = st.sidebar.radio("功能選單", page_options)
    st.session_state.page = selected_page

    if selected_page == "註冊":
        uid = st.text_input("新帳號")
        pw = st.text_input("密碼", type="password")
        if st.button("註冊"):
            from auth import register_user
            success, msg = register_user(uid, pw)
            if success:
                st.success(msg)
                st.session_state.page = "登入"
            else:
                st.error(msg)

    elif selected_page == "登入":
        uid = st.text_input("帳號")
        pw = st.text_input("密碼", type="password")
        if st.button("登入"):
            from auth import authenticate_user
            if authenticate_user(uid, pw):
                st.session_state.authenticated = True
                st.session_state.user_id = uid
                st.success("登入成功")
                st.session_state.page = "登入成功"
                st.session_state.rerun_triggered = False
                st.rerun()
            else:
                st.error("帳號或密碼錯誤")

    elif selected_page == "登記可用時間":
        date_range = pd.date_range(date.today(), periods=30).tolist()
        selected = st.multiselect("選擇可用日期", date_range, format_func=lambda d: d.strftime("%Y-%m-%d"))
        if st.button("更新"):
            update_availability(st.session_state.user_id, [d.strftime("%Y-%m-%d") for d in selected])

    elif selected_page == "查詢可配對使用者":
        df = get_df()
        st.header("查詢使用者空閒日曆")
        other_users = df[df["user_id"] != st.session_state.user_id]["user_id"].tolist()
        target = st.selectbox("選擇使用者", other_users)
        display_calendar_view(target)
        date_range = pd.date_range(date.today(), periods=30).tolist()
        selected = st.multiselect("查詢日期", date_range, format_func=lambda d: d.strftime("%Y-%m-%d"))
        for d in selected:
            users = find_users_by_date(d.strftime("%Y-%m-%d"), st.session_state.user_id)
            st.write(f"{d.strftime('%Y-%m-%d')}: {', '.join(users) if users else '無'}")

    elif selected_page == "送出好友申請":
        target = st.text_input("輸入對方 ID")
        if st.button("送出好友申請"):
            msg = send_friend_request(st.session_state.user_id, target)
            st.info(msg)

    elif selected_page == "回應好友申請":
        requests = list_friend_requests(st.session_state.user_id)
        if not requests:
            st.info("目前沒有好友申請")
        else:
            for requester in requests:
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.write(f"來自 {requester} 的好友申請")
                with col2:
                    if st.button("接受", key=f"accept_{requester}"):
                        msg = accept_friend_request(st.session_state.user_id, requester)
                        st.success(msg)
                        st.rerun()
                    if st.button("拒絕", key=f"reject_{requester}"):
                        msg = reject_friend_request(st.session_state.user_id, requester)
                        st.info(msg)
                        st.rerun()

    elif selected_page == "查看好友清單":
        show_friend_list_with_availability(st.session_state.user_id)

    elif selected_page == "群組管理":
        render_group_management_ui(st.session_state.user_id)

    elif selected_page == "管理介面" and st.session_state.user_id == "GM":
        st.subheader("GM 管理介面")
        df = get_df()
        st.dataframe(df)
        
    elif selected_page == "登出":
        st.session_state.authenticated = False
        st.session_state.user_id = ""
        st.session_state.page = "登入"
        st.success("已登出")
        st.rerun()
  # 每 60 秒自動刷新頁面
if "last_refresh_time" not in st.session_state:
    st.session_state.last_refresh_time = time.time()
elif time.time() - st.session_state.last_refresh_time > 60:
    st.session_state.last_refresh_time = time.time()
    st.rerun()

# 主畫面邏輯
from ui_module import render_ui
render_ui()
