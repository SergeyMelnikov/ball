import cymysql
from flask import Flask, url_for, render_template, request, make_response, redirect
import cgi
import hashlib
import time
import smtplib
import random
import string
import urllib
from email.mime.text import MIMEText
import json
ball = Flask (__name__)

conn = False
cur = False

base_url = 'https://acm.math.spbu.ru/ball'
vk_app_id = '12345'
vk_client_secret = 'secret'
auth_salt = 'salt'

allowed_users = ['vk:12345']

config = {
  'db': { 'host': '127.0.0.1', 'user': 'ball', 'db': 'ball', 'passwd': 'password' }
}
lang = {
  'index_title': 'Шарики',
  'index_no_events': 'Нет соревнований',
  'index_not_authorised': 'Вы не авторизованы.',
  'index_log_in': 'Войти',

  'event_header_problems': 'Задачи',
  'event_header_queue': 'Очередь',
  'event_header_your_queue': 'Вы несете',
  'event_header_offer': 'Предлагаем отнести',
  'event_queue_problem': 'Задача',
  'event_queue_team': 'Команда',
  'event_queue_take': 'Отнесу',
  'event_queue_done': 'Готово',
  'event_queue_drop': 'Отказаться',
  'event_queue_first_to_solve': '1OK ',
  'event_queue_first_solved': '1OK ',
  
  'problem_cur_color': 'Цвет сейчас',
  'problem_set_color': 'Установить цвет',

  'balloon_state_wanted': 'Нужно отнести!',
  'balloon_state_carrying': 'Несут',
  'balloon_state_delivered': 'Доставлен',

  '': ''
}

def mysql_init():
  conn = cymysql.connect( \
    host=config['db']['host'],
    user=config['db']['user'],
    passwd=config['db']['passwd'],
    db=config['db']['db'],
    charset='utf8')
  cur = conn.cursor()
  return conn, cur

def mysql_close(conn, cur):
  cur.close ()
  conn.close ()

@ball.route ('/')
def index():
  conn, cur = mysql_init()
  user_id = check_auth(request)
  content = ''
  events = []
  cur.execute('select id, name, state from events')
  for row in cur.fetchall ():
    events.append (row)
  if len(events) == 0:
    content = lang['index_no_events']
  for e in events:
    content += '<div><a href="event' + str (e[0]) + '">' + cgi.escape (e[1]) + '</a></div>'
  if user_id == None:
    content += '<div>' + lang['index_not_authorised'] + ' <a href="/ball/auth">' + lang['index_log_in'] + '</a></div>'
  else:
    content += '<div><b>' + str(user_id) + '</b></div>'
  mysql_close(conn, cur)
  return render_template('template.html', title=lang['index_title'], content=content)

@ball.route('/problem<int:problem_id>')
def problem(problem_id):
  user_id = check_auth(request)
  if not user_id in allowed_users:
    return redirect(base_url)
  conn, cur = mysql_init()
  problem_id = int(problem_id)
  content = ''
  colors = ['#f9ff0f', '#000000', '#f6ab23', '#cc0000', '#03C03C', '#e1379e', '#9e37e1', '#2FACAC', '#0047AB']
  problems = []
  cur.execute ('select id, letter, color from problems where id=%s', [problem_id])
  for row in cur.fetchall ():
    p = { 'id': row[0], 'letter': row[1], 'color': row[2] }
    problems.append (p)
  problems_html = '<h2>' + problems[0]['letter'] + '</h2>\n'
  content += problems_html
  colors_html = ''
  colors_html += '<div><span style="color:' + problems[0]['color'] + '">' + lang['problem_cur_color'] + ' <b>' + problems[0]['color'] + '</b>' + '</span></div>'
  for c in colors:
    colors_html += '<div><a href="/ball/do_set_color?problem=' + str(problem_id) + '&color=' + urllib.parse.quote(c) + '"><span style="color:' + c + '">' + lang['problem_set_color'] + ' <b>' + c + '</b>' + '</span></a></div>'
  content += colors_html
  mysql_close(conn, cur)
  return render_template('template.html', title=problems[0]['letter'], content=content)

def get_state_str_current(event_id, b):
  state_str = ''
  state_str += ' <a href="/ball/do_done?event=' + str(event_id) + '&balloon=' + str(b['id']) + '">' + lang['event_queue_done'] + '</a>'
  state_str += ' <a href="/ball/do_drop?event=' + str(event_id) + '&balloon=' + str(b['id']) + '">' + lang['event_queue_drop'] + '</a>'
  return state_str

def get_state_str_queue(event_id, b):
  state_str = ''
  if b['state'] >= 0 and b['state'] < 100:
    state_str = lang['balloon_state_wanted'] + ' <a href="/ball/do_take?event=' + str(event_id) + '&balloon=' + str(b['id']) + '">' + lang['event_queue_take'] + '</a>'
  elif b['state'] < 200:
    state_str = lang['balloon_state_carrying']
  elif b['state'] < 300:
    state_str = lang['balloon_state_delivered']
  else:
    state_str = lang['balloon_state_error']
  if str(b['volunteer_id']) != '':
    state_str += ' (' + str(b['volunteer_id']) + ')'
  return state_str

def get_balloons_html(event_id, problems, problems_map, teams, teams_map, first_to_solve, first_solved, cur, header, get_state_str):
  balloons = []
  for row in cur.fetchall ():
    b = { 'id': row[0], 'problem_id': row[1], 'team_id': row[2], 'volunteer_id': row[3], 'state': int(row[4]) }
    balloons.append (b)
  if len(balloons) == 0:
    return ''
  balloons_html = '<h2>' + header + '</h2>\n'
  balloons_html += '<table style="width: 100%;">\n'
  for b in balloons:
    p = problems[problems_map[b['problem_id']]]
    t = teams[teams_map[b['team_id']]]
    state_str = get_state_str(event_id, b)
    balloons_html += '<tr style="padding: 10px;">'
    balloons_html += '<td style="background-color: ' + p['color'] + '; width: 20px; border-style: solid; border-width: 1px;">&nbsp;</td>'
    x = ''
    if first_to_solve[b['problem_id']] == b['id']:
      x = '<b>' + lang['event_queue_first_to_solve'] + '</b>'
    balloons_html += '<td>' + x + lang['event_queue_problem'] + ' <b>' + p['letter'] + '</b></td>'
    x = ''
    if b['team_id'] in first_solved and first_solved[b['team_id']] == b['id']:
      x = '<b>' + lang['event_queue_first_solved'] + '</b>'
    balloons_html += '<td>' + x + lang['event_queue_team'] + ' <b>' + t['name'] + '</b>: ' + cgi.escape(t['long_name']) + '</td>'
    balloons_html += '<td>' + state_str + '</td>'
    balloons_html += '<tr>\n'
  balloons_html += '</table>\n'
  return balloons_html

@ball.route ('/event<int:event_id>')
def event(event_id):
  user_id = check_auth(request)
  if not user_id in allowed_users:
    return redirect(base_url)
  conn, cur = mysql_init()
  event_id = int(event_id)
  content = ''
  events = []
  cur.execute ('select id, name, state from events where id=%s', [event_id])
  for row in cur.fetchall ():
    e = row
  event = { 'name': e[1], 'state': e[2] }

  problems = []
  problems_map = {}
  cur.execute ('select id, letter, color from problems where event_id=%s', [event_id])
  for row in cur.fetchall ():
    p = { 'id': row[0], 'letter': row[1], 'color': row[2] }
    problems.append (p)
    problems_map[p['id']] = len (problems) - 1
  for p in problems:
    cur.execute('select count(*) from balloons where event_id=%s and problem_id=%s', [event_id, p['id']])
    cnt = 0
    for row in cur.fetchall():
      cnt = int(row[0])
    p['cnt'] = cnt
  problems_html = '<h2>' + lang['event_header_problems'] + '</h2>\n'
  problems_html += '<table style="width: 100%;"><tr>'
  for p in problems:
    text = '&nbsp;'
    if p['color'] == '':
      text = '?'
    problems_html += '<td style="height: 50px; width: 25px; text-align: center; background-color: ' + p['color'] + '; border-style: solid; border-width: 1px;">' + text + '</td>'
    problems_html += '<td style="height: 50px; width: 50px; text-align: left; font-weight: bold;"><a href="/ball/problem' + str (p['id']) + '">' + p['letter'] + '</a>' + '(' + str(p['cnt']) + ')' + '</td>'
  problems_html += '</tr></table>\n'
  content += problems_html

  teams = []
  teams_map = {}
  cur.execute ('select id, name, long_name from teams where event_id=%s', [event_id])
  for row in cur.fetchall ():
    t = { 'id': row[0], 'name': row[1], 'long_name': row[2] }
    teams.append (t)
    teams_map[t['id']] = len (teams) - 1

  first_to_solve = {}
  for p in problems:
    cur.execute('select id from balloons where event_id=%s and problem_id=%s order by id limit 1', [event_id, p['id']])
    for row in cur.fetchall():
      first_to_solve[p['id']] = row[0]

  first_solved = {}
  for t in teams:
    cur.execute('select id from balloons where event_id=%s and team_id=%s order by id limit 1', [event_id, t['id']])
    for row in cur.fetchall():
      first_solved[t['id']] = row[0]

  cur.execute ('select id, problem_id, team_id, volunteer_id, state from balloons where event_id=%s and state>=100 and state<200 and volunteer_id=%s order by state, id desc', [event_id, user_id])
  content += get_balloons_html(event_id, problems, problems_map, teams, teams_map, first_to_solve, first_solved, cur, lang['event_header_your_queue'], get_state_str_current)

  cur.execute ('select id, problem_id, team_id, volunteer_id, state from balloons where event_id=%s and state<100 order by state, id desc', [event_id])
  content += get_balloons_html(event_id, problems, problems_map, teams, teams_map, first_to_solve, first_solved, cur, lang['event_header_offer'], get_state_str_queue)

  cur.execute ('select id, problem_id, team_id, volunteer_id, state from balloons where event_id=%s and state>=100 order by state, id desc', [event_id])
  content += get_balloons_html(event_id, problems, problems_map, teams, teams_map, first_to_solve, first_solved, cur, lang['event_header_queue'], get_state_str_queue)

  mysql_close(conn, cur)
  return render_template('template.html', title = event['name'], content = content)

@ball.route ('/do_take')
def do_take():
  user_id = check_auth(request)
  if not user_id in allowed_users:
    return redirect(base_url)
  conn, cur = mysql_init()
  try:
    event_id = int(request.args.get('event', '0'))
    balloon_id = int(request.args.get('balloon', '0'))
  except:
    return redirect(base_url)
  cur.execute('update balloons set state=101, volunteer_id=%s where id=%s', [user_id, balloon_id])
  conn.commit()
  mysql_close(conn, cur)
  return redirect(base_url + '/event' + str(event_id))

@ball.route ('/do_done')
def do_done():
  user_id = check_auth(request)
  if not user_id in allowed_users:
    return redirect(base_url)
  conn, cur = mysql_init()
  try:
    event_id = int(request.args.get('event', '0'))
    balloon_id = int(request.args.get('balloon', '0'))
  except:
    return redirect(base_url)
  cur.execute('update balloons set state=201, volunteer_id=%s where id=%s', [user_id, balloon_id])
  conn.commit()
  mysql_close(conn, cur)
  return redirect(base_url + '/event' + str(event_id))

@ball.route ('/do_drop')
def do_drop():
  user_id = check_auth(request)
  if not user_id in allowed_users:
    return redirect(base_url)
  conn, cur = mysql_init()
  try:
    event_id = int(request.args.get('event', '0'))
    balloon_id = int(request.args.get('balloon', '0'))
  except:
    return redirect(base_url)
  cur.execute('update balloons set state=1 where id=%s', [balloon_id])
  conn.commit()
  mysql_close(conn, cur)
  return redirect(base_url + '/event' + str(event_id))

@ball.route ('/do_set_color')
def do_set_color():
  user_id = check_auth(request)
  if not user_id in allowed_users:
    return redirect(base_url)
  conn, cur = mysql_init()
  try:
    problem_id = int(request.args.get('problem', '0'))
    color = request.args.get('color', '')
  except:
    return redirect(base_url)
  cur.execute('update problems set color=%s where id=%s', [color, problem_id])
  conn.commit()
  mysql_close(conn, cur)
  return redirect(base_url + '/problem' + str(problem_id))

@ball.route('/auth')
def auth():
  return redirect( \
    'https://oauth.vk.com/authorize?client_id=' + \
    vk_app_id + '&display=page&response_type=code&redirect_uri=' + \
    base_url + '/auth_vk_step2')

def create_auth_token(user_id):
  day = int(time.time() / (24 * 60 * 60))
  return hashlib.md5((str(user_id) + ':' + str(day) + ':' + auth_salt).encode()).hexdigest()

def check_auth(request):
  try:
    user_id = request.cookies.get('ball_user_id')
    auth_token = request.cookies.get('ball_auth_token')
  except:
    return None
  if auth_token != create_auth_token(user_id):
    return None
  return user_id

@ball.route('/auth_vk_step2')
def auth_vk_step2():
  try:
    code = request.args.get('code', '')
  except:
    code = 'None'
  vk_oauth_url = \
    'https://oauth.vk.com/access_token?client_id=' + \
    vk_app_id + '&client_secret=' + vk_client_secret + \
    '&redirect_uri=' + base_url + '/auth_vk_step2&code=' + \
    code
  res = json.loads(urllib.request.urlopen(vk_oauth_url).read().decode())
  if 'error' in res:
    error_content = 'Failed auth: ' + str(res['error_description'])
    return render_template('template.html', title='Failed auth', content=error_content)
  user_id = 'vk:' + str(res['user_id'])
  auth_token = create_auth_token(user_id)
  resp = make_response(redirect(base_url))
  resp.set_cookie('ball_auth_token', auth_token)
  resp.set_cookie('ball_user_id', user_id)
  return resp

if __name__ == '__main__':
  ball.debug = False
  ball.run (host = '127.0.0.1', port = 5200)
