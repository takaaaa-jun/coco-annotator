import { createLocalVue, shallowMount } from "@vue/test-utils";
import Vuex from "vuex";
import axios from "axios";
import Auth from "@/views/Auth";
import App from "@/App";
import user from "@/store/user";

jest.mock("axios");
const localVue = createLocalVue();
localVue.use(Vuex);
const flush = () => new Promise(resolve => setImmediate(resolve));
function setup(Component, pending = false, query = {}) {
  const store = new Vuex.Store({ modules: {
    user: { ...user, state: { ...user.state, user: null, isAuthenticated: false, isAuthenticatePending: pending } },
    info: { namespaced: true, state: { totalUsers: 1, allowRegistration: true, loading: false, socket: true }, mutations: { getServerInfo() {}, socket() {}, increamentUserCount() {} } }
  }});
  const hide = jest.fn();
  const router = { push: jest.fn(), replace: jest.fn() };
  const route = { name: Component === Auth ? "authentication" : "dataset", fullPath: "/dataset/2?file_name__icontains=04001-05000", query };
  const wrapper = shallowMount(Component, { localVue, store, mocks: {
    $route: route, $router: router,
    $loading: { show: () => ({ hide }) }, $toastr: { error: jest.fn(), warning: jest.fn() }
  }});
  return { wrapper, store, router, hide };
}

describe("login flow", () => {
  beforeEach(() => jest.clearAllMocks());
  it("stays on the login form while the request is pending and after invalid credentials", async () => {
    let reject;
    axios.post.mockImplementation(() => new Promise((resolve, fail) => { reject = fail; }));
    const { wrapper, store, router, hide } = setup(Auth);
    wrapper.setData({ loginForm: { username: "sato", password: "test-password", loading: false } });
    const request = wrapper.vm.loginUser();
    await wrapper.vm.$nextTick();
    expect(store.state.user.isAuthenticatePending).toBe(true);
    expect(router.push).not.toHaveBeenCalled();
    expect(router.replace).not.toHaveBeenCalled();
    reject({ response: { status: 400, data: { message: "Could not authenticate user" } } });
    await request;
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[role="alert"]').text()).toContain("ユーザー名またはパスワード");
    expect(hide).toHaveBeenCalledTimes(1);
    expect(wrapper.vm.loginForm.loading).toBe(false);
    expect(router.replace).not.toHaveBeenCalled();
    wrapper.destroy();
  });
  it("returns to the original filtered dataset only after successful authentication", async () => {
    axios.post.mockResolvedValue({ data: { user: { username: "sato" } } });
    const redirect = "/dataset/2?file_name__icontains=04001-05000";
    const { wrapper, router } = setup(Auth, false, { redirect });
    wrapper.setData({ loginForm: { username: "sato", password: "test-password", loading: false } });
    await wrapper.vm.loginUser();
    expect(router.replace).toHaveBeenCalledWith(redirect);
    expect(router.push).not.toHaveBeenCalled();
    wrapper.destroy();
  });
  it("does not mount a protected view before session restoration or after a 401", async () => {
    let reject;
    axios.get.mockImplementation(() => new Promise((resolve, fail) => { reject = fail; }));
    const { wrapper, router } = setup(App, true);
    expect(wrapper.find('routerview-stub').exists()).toBe(false);
    expect(wrapper.find('router-view-stub').exists()).toBe(false);
    reject({ response: { status: 401 } });
    await flush();
    await wrapper.vm.$nextTick();
    expect(router.replace).toHaveBeenCalledWith({ name: "authentication", query: { redirect: "/dataset/2?file_name__icontains=04001-05000" } });
    expect(wrapper.find('routerview-stub').exists()).toBe(false);
    expect(wrapper.find('router-view-stub').exists()).toBe(false);
    wrapper.destroy();
  });
});
