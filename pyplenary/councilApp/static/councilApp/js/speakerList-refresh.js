var discussionList = document.getElementById('discussion-list');
var dragulaRooms = {};
var countdownInterval = null;
var lastCurrentByDiscussion = {};
var lastNextByDiscussion = {};

function postDiscussion(url, payload) {
	var data = new FormData();
	Object.keys(payload || {}).forEach(function(key) {
		data.append(key, payload[key]);
	});
	return fetch(url, {
		method: 'POST',
		headers: {'X-CSRFToken': getCookie('csrftoken')},
		body: data
	}).then(function(response) {
		if (!response.ok) {
			throw new Error('Request failed');
		}
		return response.json();
	});
}

function formatSeconds(seconds) {
	seconds = Math.max(0, parseInt(seconds || 0, 10));
	var mins = Math.floor(seconds / 60);
	var secs = seconds % 60;
	return mins + ':' + String(secs).padStart(2, '0');
}

function notifySpeaker(title, body) {
	if (!('Notification' in window)) {
		alert(title + '\n' + body);
		return;
	}
	if (Notification.permission === 'granted') {
		new Notification(title, {body: body});
	} else if (Notification.permission !== 'denied') {
		Notification.requestPermission().then(function(permission) {
			if (permission === 'granted') {
				new Notification(title, {body: body});
			}
		});
	}
}

function renderDelegate(delegate) {
	return delegate.name + ' (' + delegate.institution + ')';
}

function button(label, className, onClick) {
	var btn = document.createElement('button');
	btn.type = 'button';
	btn.className = className;
	btn.innerText = label;
	btn.addEventListener('click', onClick);
	return btn;
}

function renderDiscussions(discussions) {
	dragulaRooms = {};
	discussionList.innerHTML = '';

	if (discussions.length === 0) {
		var empty = document.createElement('div');
		empty.className = 'alert alert-secondary';
		empty.innerText = 'No discussions have been created yet.';
		discussionList.appendChild(empty);
		return;
	}

	discussions.forEach(function(discussion) {
		discussionList.appendChild(renderDiscussion(discussion));
	});
	startCountdowns();
	checkNotifications(discussions);
}

function renderDiscussion(discussion) {
	var card = document.createElement('div');
	card.className = 'card mb-3';
	card.dataset.discussionId = discussion.id;

	var header = document.createElement('div');
	header.className = 'card-header d-flex flex-wrap gap-2 align-items-center';
	card.appendChild(header);

	var title = document.createElement('div');
	title.style.flexGrow = '1';
	var titleText = document.createElement('strong');
	titleText.innerText = discussion.title;
	title.appendChild(titleText);
	title.appendChild(document.createTextNode(' '));
	var typeBadge = document.createElement('span');
	typeBadge.className = 'badge bg-' + (discussion.discussion_type === 'formal' ? 'primary' : 'secondary');
	typeBadge.innerText = discussion.discussion_type;
	title.appendChild(typeBadge);
	header.appendChild(title);

	var meta = document.createElement('small');
	meta.className = 'text-muted';
	meta.innerText = 'Moderator: ' + discussion.moderator.name;
	header.appendChild(meta);

	var body = document.createElement('div');
	body.className = 'card-body';
	card.appendChild(body);

	var statusRow = document.createElement('div');
	statusRow.className = 'row g-3 mb-3';
	body.appendChild(statusRow);

	var currentCol = document.createElement('div');
	currentCol.className = 'col-12 col-md-4';
	var currentHeading = document.createElement('h5');
	currentHeading.innerText = 'Current Speaker';
	currentCol.appendChild(currentHeading);
	var currentText = document.createElement('p');
	currentText.className = 'mb-1';
	currentText.innerText = discussion.current_speaker ? renderDelegate(discussion.current_speaker.delegate) : 'No current speaker';
	currentCol.appendChild(currentText);
	statusRow.appendChild(currentCol);

	var nextCol = document.createElement('div');
	nextCol.className = 'col-12 col-md-4';
	var nextHeading = document.createElement('h5');
	nextHeading.innerText = 'Next Speaker';
	nextCol.appendChild(nextHeading);
	var nextText = document.createElement('p');
	nextText.className = 'mb-1';
	nextText.innerText = discussion.next_speaker ? renderDelegate(discussion.next_speaker.delegate) : 'No next speaker';
	nextCol.appendChild(nextText);
	statusRow.appendChild(nextCol);

	var timerCol = document.createElement('div');
	timerCol.className = 'col-12 col-md-4';
	var timerHeading = document.createElement('h5');
	timerHeading.innerText = 'Timer';
	timerCol.appendChild(timerHeading);
	var timerText = document.createElement('p');
	timerText.className = 'display-6 mb-0 discussion-timer';
	timerText.dataset.running = discussion.timer_running;
	timerText.dataset.remaining = discussion.timer_remaining_seconds;
	timerText.innerText = formatSeconds(discussion.timer_remaining_seconds);
	timerCol.appendChild(timerText);
	statusRow.appendChild(timerCol);

	renderParticipantControls(body, discussion);
	renderModeratorControls(body, discussion);
	renderParticipants(body, discussion);
	renderSpeakerList(body, discussion);

	return card;
}

function renderParticipantControls(body, discussion) {
	var controls = document.createElement('div');
	controls.className = 'd-flex flex-wrap gap-2 mb-3';
	body.appendChild(controls);

	if (discussion.user_is_participant) {
		controls.appendChild(button('Leave discussion', 'btn btn-outline-secondary btn-sm', function() {
			postDiscussion('/ajax/discussionExit/', {discussionId: discussion.id});
		}));
		if (!discussion.user_is_on_speaker_list) {
			controls.appendChild(button('Join speaker queue', 'btn btn-primary btn-sm', function() {
				postDiscussion('/ajax/discussionAddSpeaker/', {discussionId: discussion.id});
			}));
		}
	} else {
		controls.appendChild(button('Join discussion', 'btn btn-success btn-sm', function() {
			postDiscussion('/ajax/discussionJoin/', {discussionId: discussion.id});
		}));
	}
}

function renderModeratorControls(body, discussion) {
	if (!discussion.user_is_moderator) {
		return;
	}

	var controls = document.createElement('div');
	controls.className = 'd-flex flex-wrap gap-2 mb-3';
	body.appendChild(controls);

	controls.appendChild(button(discussion.active ? 'Discussion active' : 'Start discussion', 'btn btn-success btn-sm', function() {
		postDiscussion('/ajax/discussionTimerAction/', {discussionId: discussion.id, action: 'activate'});
	}));
	controls.appendChild(button('Start speaker', 'btn btn-primary btn-sm', function() {
		postDiscussion('/ajax/discussionTimerAction/', {discussionId: discussion.id, action: 'start'});
	}));
	controls.appendChild(button('Pause', 'btn btn-outline-primary btn-sm', function() {
		postDiscussion('/ajax/discussionTimerAction/', {discussionId: discussion.id, action: 'pause'});
	}));
	controls.appendChild(button('Restart', 'btn btn-outline-warning btn-sm', function() {
		postDiscussion('/ajax/discussionTimerAction/', {discussionId: discussion.id, action: 'restart'});
	}));
	controls.appendChild(button('Yield / Skip', 'btn btn-outline-danger btn-sm', function() {
		postDiscussion('/ajax/discussionTimerAction/', {discussionId: discussion.id, action: 'skip'});
	}));
	controls.appendChild(button('Finish speaker', 'btn btn-outline-success btn-sm', function() {
		postDiscussion('/ajax/discussionTimerAction/', {discussionId: discussion.id, action: 'finish'});
	}));
	controls.appendChild(button('Archive', 'btn btn-outline-secondary btn-sm', function() {
		if (confirm('Archive this discussion?')) {
			postDiscussion('/ajax/discussionArchive/', {discussionId: discussion.id});
		}
	}));
}

function renderParticipants(body, discussion) {
	var details = document.createElement('details');
	details.className = 'mb-3';
	body.appendChild(details);

	var summary = document.createElement('summary');
	summary.innerText = 'Participants (' + discussion.participants.length + ')';
	details.appendChild(summary);

	var list = document.createElement('div');
	list.className = 'd-flex flex-wrap gap-2 mt-2';
	details.appendChild(list);

	discussion.participants.forEach(function(participant) {
		var item = document.createElement('span');
		item.className = 'badge bg-light text-dark border';
		item.innerText = renderDelegate(participant.delegate);
		list.appendChild(item);

		if (discussion.user_is_moderator) {
			var addBtn = button('+ speaker', 'btn btn-sm btn-outline-primary ms-1', function() {
				postDiscussion('/ajax/discussionAddSpeaker/', {discussionId: discussion.id, delegateId: participant.delegate.id});
			});
			list.appendChild(addBtn);
		}
	});
}

function renderSpeakerList(body, discussion) {
	var heading = document.createElement('h5');
	heading.innerText = 'Speaker Queue';
	body.appendChild(heading);

	var list = document.createElement('div');
	list.className = 'list-group discussion-speaker-list';
	list.dataset.discussionId = discussion.id;
	body.appendChild(list);

	var liveSpeakers = discussion.speakers.filter(function(speaker) {
		return speaker.status === 'waiting' || speaker.status === 'current';
	});

	if (liveSpeakers.length === 0) {
		var empty = document.createElement('div');
		empty.className = 'alert alert-secondary';
		empty.innerText = 'No speakers are queued.';
		list.appendChild(empty);
		return;
	}

	liveSpeakers.forEach(function(speaker) {
		var item = document.createElement('div');
		item.className = 'list-group-item';
		if (speaker.status === 'current') {
			item.classList.add('list-group-item-success');
		}
		item.dataset.speakerId = speaker.id;
		list.appendChild(item);

		var top = document.createElement('div');
		top.className = 'd-flex flex-wrap gap-2 align-items-center';
		item.appendChild(top);

		var name = document.createElement('strong');
		name.style.flexGrow = '1';
		name.innerText = renderDelegate(speaker.delegate);
		top.appendChild(name);

		var status = document.createElement('span');
		status.className = 'badge bg-' + (speaker.status === 'current' ? 'success' : 'secondary');
		status.innerText = speaker.status;
		top.appendChild(status);

		if (discussion.user_is_moderator) {
			var input = document.createElement('input');
			input.type = 'number';
			input.min = 15;
			input.max = 900;
			input.step = 15;
			input.value = speaker.duration_seconds;
			input.className = 'form-control form-control-sm';
			input.style.width = '6rem';
			input.title = 'Speaker seconds';
			input.addEventListener('change', function() {
				postDiscussion('/ajax/discussionUpdateSpeakerTime/', {speakerId: speaker.id, durationSeconds: input.value});
			});
			top.appendChild(input);

			top.appendChild(button('Remove', 'btn btn-sm btn-outline-danger', function() {
				postDiscussion('/ajax/discussionRemoveSpeaker/', {speakerId: speaker.id});
			}));
		} else {
			var duration = document.createElement('span');
			duration.className = 'text-muted';
			duration.innerText = formatSeconds(speaker.duration_seconds);
			top.appendChild(duration);
		}
	});

	if (discussion.user_is_moderator) {
		var dragulaSL = dragula([list], {
			moves: function(el) {
				return !el.classList.contains('list-group-item-success') && el.dataset.speakerId;
			}
		});
		dragulaSL.on('drop', function() {
			var order = Array.from(list.querySelectorAll('.list-group-item[data-speaker-id]'))
				.filter(function(el) { return !el.classList.contains('list-group-item-success'); })
				.map(function(el) { return el.dataset.speakerId; })
				.join(',');
			postDiscussion('/ajax/discussionReorderSpeakers/', {discussionId: discussion.id, order: order});
		});
		dragulaRooms[discussion.id] = dragulaSL;
	}
}

function startCountdowns() {
	if (countdownInterval) {
		clearInterval(countdownInterval);
	}
	countdownInterval = setInterval(function() {
		document.querySelectorAll('.discussion-timer').forEach(function(el) {
			var remaining = parseInt(el.dataset.remaining || '0', 10);
			if (el.dataset.running === 'true' && remaining > 0) {
				remaining -= 1;
				el.dataset.remaining = remaining;
				el.innerText = formatSeconds(remaining);
			}
		});
	}, 1000);
}

function checkNotifications(discussions) {
	discussions.forEach(function(discussion) {
		var currentId = discussion.current_speaker ? discussion.current_speaker.delegate.id : null;
		var nextId = discussion.next_speaker ? discussion.next_speaker.delegate.id : null;

		if (currentId === delegate_id && lastCurrentByDiscussion[discussion.id] !== currentId) {
			notifySpeaker('You are speaking now', discussion.title);
		}
		if (nextId === delegate_id && lastNextByDiscussion[discussion.id] !== nextId) {
			notifySpeaker('You are next to speak', discussion.title);
		}

		lastCurrentByDiscussion[discussion.id] = currentId;
		lastNextByDiscussion[discussion.id] = nextId;
	});
}

var ws = new WebSocket(
	(window.location.protocol === 'https:' ? 'wss://' : 'ws://')
	+ window.location.host
	+ '/ws/speaker-list/'
);

ws.onmessage = function(event) {
	var data = JSON.parse(event.data);
	if (data.type === 'init' || data.type === 'discussions_updated') {
		renderDiscussions(data.discussions);
	}
};
