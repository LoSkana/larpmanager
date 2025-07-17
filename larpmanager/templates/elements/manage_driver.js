{% load i18n static %}

<script src="{% static 'node_modules/driver.js/dist/driver.js.iife.js' %}"
            defer></script>

    <script>
document.addEventListener('DOMContentLoaded', () => {

function driverIntro() {
const driver = window.driver.js.driver;

const driverObj = driver({
  showProgress: true,
  steps: [
    { popover: { title: '{% trans "Welcome to" %} {{ assoc.platform }}!', description: '{% trans "Here is a step-by-step walkthrough of the interface" %}' } },
    { element: '#sidebar', popover: { title: 'Sidebar', description: '{% trans "This is the sidebar containing all the functions needed to manage your organization (it remains visible on every management page)" %}', side: "right", align: 'start' }},
    { element: '#select_workspace', popover: { title: 'Workspace selector', description: '{% trans "Here you can select the workspace to use: your organization, and your events once created" %}', side: "bottom", align: 'start' }},
    { element: '#select_side', popover: { title: 'Side selector', description: '{% trans "Here you can switch between administration pages and user-facing pages" %}', side: "bottom", align: 'start' }},
    { element: '#sidebar-open', popover: { title: 'Sidebar toggle', description: '{% trans "Toggle the sidebar visibility" %}', side: "bottom", align: 'start' }},
    { element: '#tutorial_query', popover: { title: 'What would you like to do?', description: '{% trans "If you need help, type your request here in English using single keywords" %}', side: "bottom", align: 'start' }},
    { element: '#actions', popover: { title: 'Actions', description: '{% trans "Here is a to-do list of actions for managing your organization" %}', side: "top", align: 'start' }},
    { element: '#suggestions', popover: { title: 'Suggestions', description: '{% trans "And here is a to-do list of suggestions to help you set everything up properly" %}', side: "top", align: 'start' }},
    { element: '.feature_tutorial', popover: { title: 'Tutorials', description: '{% trans "Click the tutorial to open it and follow the step-by-step instructions" %}', side: "top", align: 'start' }},
    { popover: { title: '{% trans "And that is all" %}', description: '{% trans "Write to us if you need help in setting things up!" %}' } }
  ]
});

  driverObj.drive();

  }

  {% if intro_driver %} driverIntro();{% endif %}
});

    </script>
