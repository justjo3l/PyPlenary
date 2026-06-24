var discussionList = document.getElementById('discussion-list');
var discussionDetail = document.getElementById('discussion-detail');
var pageMode = discussionDetail ? 'detail' : 'list';
var dragulaRoom = null;
var countdownInterval = null;
var lastCurrentByDiscussion = {};
var lastNextByDiscussion = {};
var latestDiscussions = [];
var confirmedDiscussions = [];

function postDiscussion(url, payload, optimistic) {
	if (optimistic) {
		optimistic();
	}
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
	}).then(function(data) {
		if (data.raise404) {
			throw new Error(data.error || 'Request failed');
		}
		return data;
	}).catch(function(error) {
		if (confirmedDiscussions.length > 0) {
			renderDiscussions(confirmedDiscussions);
		}
		throw error;
	});
}

function optimisticPatchDiscussion(discussionId, mutator) {
	latestDiscussions = latestDiscussions.map(function(discussion) {
		if (discussion.id !== discussionId) {
			return discussion;
		}
		var copy = JSON.parse(JSON.stringify(discussion));
		mutator(copy);
		return copy;
	});
	if (pageMode === 'detail') {
		var selected = latestDiscussions.find(function(item) { return item.id === discussion_id; });
		renderDiscussionDetail(selected);
	} else {
		renderDiscussionList(latestDiscussions);
	}
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

function roleBadge(delegate) {
	var badge = document.createElement('span');
	var colors = {
		viewer: 'bg-secondary',
		delegate: 'bg-info text-dark',
		representative: 'bg-primary',
		moderator: 'bg-success',
		admin: 'bg-danger'
	};
	badge.className = 'badge ' + (colors[delegate.account_role] || 'bg-secondary');
	badge.innerText = delegate.account_role_label;
	return badge;
}

function button(label, className, onClick) {
	var btn = document.createElement('button');
	btn.type = 'button';
	btn.className = className;
	btn.innerText = label;
	btn.addEventListener('click', onClick);
	return btn;
}

function appendBadge(parent, text, className) {
	var badge = document.createElement('span');
	badge.className = className;
	badge.innerText = text;
	parent.appendChild(badge);
	return badge;
}

function delegateCanSpeakInDiscussion(delegate, discussion) {
	if (delegate.account_role === 'viewer') {
		return false;
	}
	if (discussion.discussion_type === 'formal') {
		return delegate.account_role === 'representative' || delegate.account_role === 'admin';
	}
	return ['delegate', 'representative', 'moderator', 'admin'].includes(delegate.account_role);
}

function renderDiscussions(discussions) {
	latestDiscussions = discussions;
	confirmedDiscussions = JSON.parse(JSON.stringify(discussions));
	if (pageMode === 'detail') {
		var selected = discussions.find(function(item) { return item.id === discussion_id; });
		renderDiscussionDetail(selected);
	} else {
		renderDiscussionList(discussions);
	}
	checkNotifications(discussions);
}

function renderDiscussionList(discussions) {
	discussionList.innerHTML = '';

	if (discussions.length === 0) {
		var empty = document.createElement('div');
		empty.className = 'alert alert-secondary';
		empty.innerText = 'No discussions have been created yet.';
		discussionList.appendChild(empty);
		return;
	}

	var rows = document.createElement('div');
	rows.className = 'list-group';
	discussionList.appendChild(rows);

	discussions.forEach(function(discussion) {
		var link = document.createElement('a');
		link.href = '/discussions/' + discussion.id + '/';
		link.className = 'list-group-item list-group-item-action';
		rows.appendChild(link);

		var top = document.createElement('div');
		top.className = 'd-flex flex-wrap gap-2 align-items-center';
		link.appendChild(top);

		var title = document.createElement('strong');
		title.style.flexGrow = '1';
		title.innerText = discussion.title;
		top.appendChild(title);

		appendBadge(top, discussion.discussion_type, 'badge bg-' + (discussion.discussion_type === 'formal' ? 'primary' : 'secondary'));
		appendBadge(top, discussion.status, 'badge bg-' + (discussion.status === 'active' ? 'success' : (discussion.status === 'closed' ? 'dark' : 'warning text-dark')));

	var meta = document.createElement('div');
	meta.className = 'small text-muted mt-1';
	meta.innerText = 'Moderator: ' + discussion.moderator.name + ' (' + discussion.moderator.account_role_label + ') · People in discussion: ' + discussion.participant_count;
	link.appendChild(meta);
	});
}

function renderDiscussionDetail(discussion) {
	if (dragulaRoom) {
		dragulaRoom.destroy();
		dragulaRoom = null;
	}
	if (countdownInterval) {
		clearInterval(countdownInterval);
		countdownInterval = null;
	}
	discussionDetail.innerHTML = '';

	if (!discussion) {
		var missing = document.createElement('div');
		missing.className = 'alert alert-warning';
		missing.innerText = 'This discussion could not be found.';
		discussionDetail.appendChild(missing);
		return;
	}

	var header = document.createElement('div');
	header.className = 'mb-4';
	discussionDetail.appendChild(header);

	var heading = document.createElement('div');
	heading.className = 'd-flex flex-wrap gap-2 align-items-center mb-2';
	header.appendChild(heading);

	var title = document.createElement('h2');
	title.className = 'mb-0';
	title.style.flexGrow = '1';
	title.innerText = discussion.title;
	heading.appendChild(title);

	appendBadge(heading, discussion.discussion_type, 'badge bg-' + (discussion.discussion_type === 'formal' ? 'primary' : 'secondary'));
	appendBadge(heading, discussion.status, 'badge bg-' + (discussion.status === 'active' ? 'success' : (discussion.status === 'closed' ? 'dark' : 'warning text-dark')));

	var meta = document.createElement('p');
	meta.className = 'text-muted mb-0';
	meta.innerText = 'Original moderator: ' + discussion.moderator.name + ' (' + discussion.moderator.account_role_label + ') · People in discussion: ' + discussion.participant_count;
	header.appendChild(meta);

	renderSpeakerFocus(discussion);
	renderParticipantControls(discussion);
	renderModeratorPanel(discussion);
	renderParticipants(discussion);
	renderSpeakerList(discussion);
	renderQuestionBox(discussion);
	startCountdown();
}

function renderSpeakerFocus(discussion) {
	var panel = document.createElement('div');
	panel.className = 'text-center my-4';
	discussionDetail.appendChild(panel);

	var currentLabel = document.createElement('div');
	currentLabel.className = 'text-muted text-uppercase small';
	currentLabel.innerText = 'Current Speaker';
	panel.appendChild(currentLabel);

	var current = document.createElement('div');
	current.className = 'display-5 fw-bold';
	current.innerText = discussion.current_speaker ? renderDelegate(discussion.current_speaker.delegate) : 'No current speaker';
	panel.appendChild(current);

	var next = document.createElement('div');
	next.className = 'h5 text-muted mt-3';
	next.innerText = discussion.next_speaker ? 'Next: ' + renderDelegate(discussion.next_speaker.delegate) : 'Next: no speaker queued';
	panel.appendChild(next);

	var timer = document.createElement('div');
	timer.className = 'display-3 mt-4 discussion-timer';
	timer.dataset.running = discussion.timer_running;
	timer.dataset.remaining = discussion.timer_remaining_seconds;
	timer.innerText = formatSeconds(discussion.timer_remaining_seconds);
	panel.appendChild(timer);

	if (discussion.user_is_moderator && discussion.status !== 'closed') {
		var controls = document.createElement('div');
		controls.className = 'd-flex flex-wrap justify-content-center gap-2 mt-3';
		panel.appendChild(controls);

		if (!discussion.speaker_timer_started) {
			controls.appendChild(button('Start speaker', 'btn btn-primary btn-sm', function() {
				postDiscussion('/ajax/discussionTimerAction/', {discussionId: discussion.id, action: 'start'}, function() {
					optimisticPatchDiscussion(discussion.id, function(copy) {
						copy.speaker_timer_started = true;
						copy.timer_running = true;
						copy.active = true;
						copy.status = 'active';
					});
				});
			}));
		} else if (discussion.timer_running) {
			controls.appendChild(button('Pause', 'btn btn-outline-primary btn-sm', function() {
				var remaining = parseInt((document.querySelector('.discussion-timer') || {}).dataset.remaining || discussion.timer_remaining_seconds, 10);
				postDiscussion('/ajax/discussionTimerAction/', {discussionId: discussion.id, action: 'pause'}, function() {
					optimisticPatchDiscussion(discussion.id, function(copy) {
						copy.timer_running = false;
						copy.timer_remaining_seconds = remaining;
					});
				});
			}));
		} else {
			controls.appendChild(button('Resume', 'btn btn-primary btn-sm', function() {
				postDiscussion('/ajax/discussionTimerAction/', {discussionId: discussion.id, action: 'resume'}, function() {
					optimisticPatchDiscussion(discussion.id, function(copy) {
						copy.timer_running = true;
					});
				});
			}));
		}
		controls.appendChild(button('Restart', 'btn btn-outline-warning btn-sm', function() {
			postDiscussion('/ajax/discussionTimerAction/', {discussionId: discussion.id, action: 'restart'}, function() {
				optimisticPatchDiscussion(discussion.id, function(copy) {
					copy.timer_running = true;
					copy.timer_remaining_seconds = copy.current_speaker ? copy.current_speaker.duration_seconds : copy.default_speaker_seconds;
				});
			});
		}));
		controls.appendChild(button('Yield / Skip', 'btn btn-outline-danger btn-sm', function() {
			postDiscussion('/ajax/discussionTimerAction/', {discussionId: discussion.id, action: 'skip'}, function() {
				optimisticPatchDiscussion(discussion.id, function(copy) {
					copy.speaker_timer_started = false;
					copy.timer_running = false;
					copy.timer_remaining_seconds = copy.default_speaker_seconds;
					copy.speakers = copy.speakers.filter(function(speaker) { return !copy.current_speaker || speaker.id !== copy.current_speaker.id; });
					copy.current_speaker = copy.speakers.find(function(speaker) { return speaker.status === 'waiting'; }) || null;
				});
			});
		}));
		controls.appendChild(button('Finish speaker', 'btn btn-outline-success btn-sm', function() {
			postDiscussion('/ajax/discussionTimerAction/', {discussionId: discussion.id, action: 'finish'}, function() {
				optimisticPatchDiscussion(discussion.id, function(copy) {
					copy.speaker_timer_started = false;
					copy.timer_running = false;
					copy.timer_remaining_seconds = copy.default_speaker_seconds;
					copy.speakers = copy.speakers.filter(function(speaker) { return !copy.current_speaker || speaker.id !== copy.current_speaker.id; });
					copy.current_speaker = copy.speakers.find(function(speaker) { return speaker.status === 'waiting'; }) || null;
				});
			});
		}));
	}
}

function renderParticipantControls(discussion) {
	var controls = document.createElement('div');
	controls.className = 'd-flex flex-wrap gap-2 mb-3';
	discussionDetail.appendChild(controls);

	if (discussion.status === 'closed') {
		var closed = document.createElement('div');
		closed.className = 'alert alert-secondary w-100';
		closed.innerText = 'This discussion is closed.';
		controls.appendChild(closed);
		return;
	}

	if (discussion.user_is_participant) {
		if (discussion.moderator.id !== delegate_id) {
			controls.appendChild(button('Leave discussion', 'btn btn-outline-secondary btn-sm', function() {
				postDiscussion('/ajax/discussionExit/', {discussionId: discussion.id});
			}));
		}
		if (!discussion.user_is_on_speaker_queue && discussion.user_can_speak) {
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

function renderModeratorPanel(discussion) {
	if (!discussion.user_is_moderator) {
		return;
	}

	var panel = document.createElement('div');
	panel.className = 'border rounded p-3 mb-3';
	discussionDetail.appendChild(panel);

	var title = document.createElement('h5');
	title.innerText = 'Moderator Controls';
	panel.appendChild(title);

	var controls = document.createElement('div');
	controls.className = 'd-flex flex-wrap gap-2 mb-3';
	panel.appendChild(controls);

	var rename = document.createElement('input');
	rename.type = 'text';
	rename.value = discussion.title;
	rename.maxLength = 200;
	rename.className = 'form-control form-control-sm';
	rename.style.maxWidth = '18rem';
	controls.appendChild(rename);
	controls.appendChild(button('Rename', 'btn btn-outline-primary btn-sm', function() {
		var title = rename.value.trim();
		postDiscussion('/ajax/discussionRename/', {discussionId: discussion.id, title: title}, function() {
			optimisticPatchDiscussion(discussion.id, function(copy) {
				copy.title = title || copy.title;
			});
		});
	}));

	if (discussion.status === 'closed') {
		controls.appendChild(button('Reopen discussion', 'btn btn-success btn-sm', function() {
			postDiscussion('/ajax/discussionReopen/', {discussionId: discussion.id}, function() {
				optimisticPatchDiscussion(discussion.id, function(copy) {
					copy.archived = false;
					copy.status = copy.active ? 'active' : 'pending';
				});
			});
		}));
	} else if (!discussion.active) {
		controls.appendChild(button('Start discussion', 'btn btn-success btn-sm', function() {
			postDiscussion('/ajax/discussionTimerAction/', {discussionId: discussion.id, action: 'activate'}, function() {
				optimisticPatchDiscussion(discussion.id, function(copy) {
					copy.active = true;
					copy.status = 'active';
				});
			});
		}));
	}
	if (discussion.status !== 'closed') {
		var typeSelect = document.createElement('select');
		typeSelect.className = 'form-select form-select-sm';
		typeSelect.style.maxWidth = '12rem';
		[['informal', 'Informal'], ['formal', 'Formal']].forEach(function(item) {
			var option = document.createElement('option');
			option.value = item[0];
			option.innerText = item[1];
			option.selected = discussion.discussion_type === item[0];
			typeSelect.appendChild(option);
		});
		typeSelect.addEventListener('change', function() {
			postDiscussion('/ajax/discussionTypeChange/', {discussionId: discussion.id, discussionType: typeSelect.value}, function() {
				optimisticPatchDiscussion(discussion.id, function(copy) {
					copy.discussion_type = typeSelect.value;
				});
			});
		});
		controls.appendChild(typeSelect);
		controls.appendChild(button('Close discussion', 'btn btn-outline-secondary btn-sm', function() {
			if (confirm('Close this discussion?')) {
				postDiscussion('/ajax/discussionArchive/', {discussionId: discussion.id}, function() {
					optimisticPatchDiscussion(discussion.id, function(copy) {
						copy.archived = true;
						copy.active = false;
						copy.timer_running = false;
						copy.status = 'closed';
					});
				});
			}
		}));
	}

	var moderators = document.createElement('p');
	moderators.className = 'mb-2';
	var names = [discussion.moderator.name].concat(discussion.additional_moderators.map(function(moderator) { return moderator.name; }));
	moderators.innerText = 'Moderators: ' + names.join(', ');
	panel.appendChild(moderators);

	if (discussion.status !== 'closed' && discussion.user_can_manage_moderators && discussion.moderator_options.length > 0) {
		var addRow = document.createElement('div');
		addRow.className = 'd-flex flex-wrap gap-2 align-items-center';
		panel.appendChild(addRow);

		var select = document.createElement('select');
		select.className = 'form-select form-select-sm';
		select.style.maxWidth = '18rem';
		discussion.moderator_options.forEach(function(option) {
			var opt = document.createElement('option');
			opt.value = option.id;
			opt.innerText = renderDelegate(option);
			select.appendChild(opt);
		});
		addRow.appendChild(select);

		addRow.appendChild(button('Add Moderator', 'btn btn-outline-primary btn-sm', function() {
			postDiscussion('/ajax/discussionAddModerator/', {discussionId: discussion.id, delegateId: select.value});
		}));
	}

	var logLink = document.createElement('a');
	logLink.href = '/discussions/' + discussion.id + '/logs/';
	logLink.className = 'btn btn-outline-dark btn-sm';
	logLink.innerText = 'Logs';
	panel.appendChild(logLink);
}

function renderParticipants(discussion) {
	var details = document.createElement('details');
	details.className = 'mb-3';
	discussionDetail.appendChild(details);

	var summary = document.createElement('summary');
	summary.innerText = 'Participants (' + discussion.participants.length + ')';
	details.appendChild(summary);

	var list = document.createElement('div');
	list.className = 'd-flex flex-wrap gap-2 mt-2';
	details.appendChild(list);

	discussion.participants.forEach(function(participant) {
		var item = document.createElement('span');
		item.className = 'badge bg-light text-dark border';
		item.innerText = renderDelegate(participant.delegate) + ' ';
		item.appendChild(roleBadge(participant.delegate));
		list.appendChild(item);

		if (discussion.user_is_moderator && discussion.status !== 'closed' && participant.delegate.id !== delegate_id && delegateCanSpeakInDiscussion(participant.delegate, discussion)) {
			var addBtn = button('+ speaker', 'btn btn-sm btn-outline-primary ms-1', function() {
				postDiscussion('/ajax/discussionAddSpeaker/', {discussionId: discussion.id, delegateId: participant.delegate.id});
			});
			list.appendChild(addBtn);
		}
	});
}

function renderSpeakerList(discussion) {
	var heading = document.createElement('h5');
	heading.innerText = 'Speaker Queue';
	discussionDetail.appendChild(heading);

	var list = document.createElement('div');
	list.className = 'list-group discussion-speaker-list mb-3';
	list.dataset.discussionId = discussion.id;
	discussionDetail.appendChild(list);

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
		top.appendChild(roleBadge(speaker.delegate));

		appendBadge(top, speaker.status, 'badge bg-' + (speaker.status === 'current' ? 'success' : 'secondary'));

		if (discussion.user_is_moderator && discussion.status !== 'closed') {
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
		} else {
			var duration = document.createElement('span');
			duration.className = 'text-muted';
			duration.innerText = formatSeconds(speaker.duration_seconds);
			top.appendChild(duration);
		}

		if (discussion.status !== 'closed' && (discussion.user_is_moderator || speaker.delegate.id === delegate_id)) {
			top.appendChild(button(speaker.delegate.id === delegate_id ? 'Exit queue' : 'Remove', 'btn btn-sm btn-outline-danger', function() {
				postDiscussion('/ajax/discussionRemoveSpeaker/', {speakerId: speaker.id});
			}));
		}
	});

	if (discussion.user_is_moderator && discussion.status !== 'closed' && typeof dragula !== 'undefined') {
		dragulaRoom = dragula([list], {
			moves: function(el) {
				return !el.classList.contains('list-group-item-success') && el.dataset.speakerId;
			}
		});
		dragulaRoom.on('drop', function() {
			var order = Array.from(list.querySelectorAll('.list-group-item[data-speaker-id]'))
				.filter(function(el) { return !el.classList.contains('list-group-item-success'); })
				.map(function(el) { return el.dataset.speakerId; })
				.join(',');
			postDiscussion('/ajax/discussionReorderSpeakers/', {discussionId: discussion.id, order: order});
		});
	}
}

function renderQuestionBox(discussion) {
	var section = document.createElement('div');
	section.className = 'mt-4';
	discussionDetail.appendChild(section);

	var heading = document.createElement('h5');
	heading.innerText = 'Q&A';
	section.appendChild(heading);

	if (discussion.status !== 'closed') {
		var form = document.createElement('form');
		form.className = 'mb-3';
		section.appendChild(form);

		var textarea = document.createElement('textarea');
		textarea.className = 'form-control mb-2';
		textarea.rows = 3;
		textarea.maxLength = 2000;
		textarea.placeholder = 'Ask a question';
		form.appendChild(textarea);

		var actions = document.createElement('div');
		actions.className = 'd-flex flex-wrap gap-2';
		form.appendChild(actions);

		actions.appendChild(button('Post', 'btn btn-primary btn-sm', function() {
			submitQuestion(discussion, textarea, '');
		}));

		form.addEventListener('submit', function(event) {
			event.preventDefault();
		});
	}

	var list = document.createElement('div');
	list.className = 'list-group';
	section.appendChild(list);

	if (!discussion.questions || discussion.questions.length === 0) {
		var empty = document.createElement('div');
		empty.className = 'alert alert-secondary';
		empty.innerText = 'No questions yet.';
		list.appendChild(empty);
		return;
	}

	var byParent = {};
	discussion.questions.forEach(function(question) {
		var parentId = question.parent_id || 'root';
		if (!byParent[parentId]) {
			byParent[parentId] = [];
		}
		byParent[parentId].push(question);
	});

	(byParent.root || []).forEach(function(question) {
		renderQuestionItem(list, discussion, question, byParent, 0);
	});
}

function renderQuestionItem(list, discussion, question, byParent, depth) {
	var item = document.createElement('div');
	item.className = 'list-group-item';
	if (depth > 0) {
		item.style.marginLeft = Math.min(depth, 3) * 1.5 + 'rem';
	}
	list.appendChild(item);

	var meta = document.createElement('div');
	meta.className = 'small text-muted mb-1';
	meta.innerText = question.author.name + ' · ' + question.author.account_role_label + ' · ' + new Date(question.created_at).toLocaleString();
	item.appendChild(meta);

	var text = document.createElement('div');
	text.innerText = question.text;
	item.appendChild(text);

	var actions = document.createElement('div');
	actions.className = 'd-flex flex-wrap gap-2 mt-2';
	item.appendChild(actions);

	renderReactionSummary(actions, question);
	renderReactionPicker(actions, question);

	if (discussion.status !== 'closed') {
		actions.appendChild(button('Reply', 'btn btn-outline-secondary btn-sm', function() {
			renderInlineReplyForm(item, discussion, question);
		}));
		if (question.author.id === delegate_id) {
			actions.appendChild(button('Edit', 'btn btn-outline-secondary btn-sm', function() {
				renderInlineEditForm(item, discussion, question, text);
			}));
			actions.appendChild(button('Delete', 'btn btn-outline-danger btn-sm', function() {
				if (confirm('Delete this Q&A message?')) {
					postDiscussion('/ajax/discussionQuestionDelete/', {questionId: question.id}, function() {
						optimisticPatchDiscussion(discussion.id, function(copy) {
							copy.questions = copy.questions.filter(function(item) {
								return item.id !== question.id && item.parent_id !== question.id;
							});
						});
					});
				}
			}));
		}
	}

	(byParent[question.id] || []).forEach(function(reply) {
		renderQuestionItem(list, discussion, reply, byParent, depth + 1);
	});
}

function submitQuestion(discussion, textarea, parentId) {
	var text = textarea.value.trim();
	if (!text) {
		return;
	}
	postDiscussion('/ajax/discussionQuestionAdd/', {
		discussionId: discussion.id,
		parentId: parentId,
		text: text
	}, function() {
		optimisticPatchDiscussion(discussion.id, function(copy) {
			copy.questions.push({
				id: 'tmp-' + Date.now(),
				discussion_id: discussion.id,
				author: {id: delegate_id, name: 'You', institution: '', account_role: '', account_role_label: 'You'},
				parent_id: parentId || null,
				text: text,
				created_at: new Date().toISOString(),
				reaction_counts: {},
				user_reactions: []
			});
		});
	});
	textarea.value = '';
}

function renderInlineReplyForm(item, discussion, question) {
	document.querySelectorAll('.inline-reply-form').forEach(function(form) {
		form.remove();
	});
	var existing = item.querySelector('.inline-reply-form');
	if (existing) {
		existing.querySelector('textarea').focus();
		return;
	}
	var form = document.createElement('div');
	form.className = 'inline-reply-form border rounded p-2 mt-2 bg-light';
	item.appendChild(form);

	var header = document.createElement('div');
	header.className = 'd-flex align-items-center mb-2';
	form.appendChild(header);

	var label = document.createElement('div');
	label.className = 'small text-muted';
	label.style.flexGrow = '1';
	label.innerText = 'Replying to ' + question.author.name;
	header.appendChild(label);

	header.appendChild(button('×', 'btn btn-sm btn-outline-secondary', function() {
		form.remove();
	}));

	var textarea = document.createElement('textarea');
	textarea.className = 'form-control form-control-sm mb-2';
	textarea.rows = 2;
	textarea.maxLength = 2000;
	textarea.placeholder = 'Write a reply';
	form.appendChild(textarea);

	var actions = document.createElement('div');
	actions.className = 'd-flex gap-2';
	form.appendChild(actions);

	actions.appendChild(button('Reply', 'btn btn-primary btn-sm', function() {
		submitQuestion(discussion, textarea, question.id);
		form.remove();
	}));
	textarea.focus();
}

function renderInlineEditForm(item, discussion, question, textElement) {
	document.querySelectorAll('.inline-edit-form').forEach(function(form) {
		form.remove();
	});
	var form = document.createElement('div');
	form.className = 'inline-edit-form border rounded p-2 mt-2 bg-light';
	item.appendChild(form);

	var header = document.createElement('div');
	header.className = 'd-flex align-items-center mb-2';
	form.appendChild(header);

	var label = document.createElement('div');
	label.className = 'small text-muted';
	label.style.flexGrow = '1';
	label.innerText = 'Editing your message';
	header.appendChild(label);

	header.appendChild(button('×', 'btn btn-sm btn-outline-secondary', function() {
		form.remove();
	}));

	var textarea = document.createElement('textarea');
	textarea.className = 'form-control form-control-sm mb-2';
	textarea.rows = 2;
	textarea.maxLength = 2000;
	textarea.value = question.text;
	form.appendChild(textarea);

	var actions = document.createElement('div');
	actions.className = 'd-flex gap-2';
	form.appendChild(actions);

	actions.appendChild(button('Save', 'btn btn-primary btn-sm', function() {
		var nextText = textarea.value.trim();
		if (!nextText) {
			return;
		}
		postDiscussion('/ajax/discussionQuestionEdit/', {questionId: question.id, text: nextText}, function() {
			optimisticPatchDiscussion(discussion.id, function(copy) {
				copy.questions.forEach(function(item) {
					if (item.id === question.id) {
						item.text = nextText;
					}
				});
			});
		});
		textElement.innerText = nextText;
		form.remove();
	}));
	textarea.focus();
}

function reactionMeta() {
	return [
		['heart', 'Heart', '♥'],
		['thumbs_up', 'Thumbs up', '👍'],
		['thumbs_down', 'Thumbs down', '👎'],
		['question', 'Question', '?']
	];
}

function renderReactionSummary(parent, question) {
	var summary = document.createElement('div');
	summary.className = 'd-flex flex-wrap gap-1 align-items-center';
	parent.appendChild(summary);

	reactionMeta().forEach(function(reaction) {
		var key = reaction[0];
		var icon = reaction[2];
		var count = question.reaction_counts[key] || 0;
		if (count > 0) {
			var pill = document.createElement('span');
			pill.className = 'badge rounded-pill bg-light text-dark border';
			pill.innerText = icon + ' ' + count;
			summary.appendChild(pill);
		}
	});
}

function renderReactionPicker(parent, question) {
	var wrapper = document.createElement('div');
	wrapper.className = 'dropdown';
	parent.appendChild(wrapper);

	var trigger = button('React', 'btn btn-outline-primary btn-sm dropdown-toggle', function() {});
	trigger.setAttribute('data-bs-toggle', 'dropdown');
	wrapper.appendChild(trigger);

	var menu = document.createElement('div');
	menu.className = 'dropdown-menu p-1';
	wrapper.appendChild(menu);

	reactionMeta().forEach(function(reaction) {
		var key = reaction[0];
		var label = reaction[1];
		var icon = reaction[2];
		var active = question.user_reactions.indexOf(key) !== -1;
		var item = button(icon + ' ' + label, active ? 'dropdown-item active' : 'dropdown-item', function() {
			postDiscussion('/ajax/discussionQuestionReact/', {questionId: question.id, reaction: key});
		});
		menu.appendChild(item);
	});
}

function startCountdown() {
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

		if (discussion.speaker_timer_started && currentId === delegate_id && lastCurrentByDiscussion[discussion.id] !== currentId) {
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
